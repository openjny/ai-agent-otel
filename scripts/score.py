#!/usr/bin/env python3
"""Score a single trace using Copilot SDK as LLM-as-Judge.

Usage:
    # Score the most recent trace
    uv run scripts/score.py

    # Score a specific trace
    uv run scripts/score.py --trace-id 7ba34e3871de

    # Dry-run: print the prompt without calling copilot
    uv run scripts/score.py --dry-run
"""
# /// script
# requires-python = ">=3.11"
# dependencies = ["duckdb", "github-copilot-sdk"]
# ///

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import textwrap
from pathlib import Path

import duckdb

DATA_DIR = Path(__file__).parent.parent / "data"


def extract_trace(trace_id: str | None) -> dict:
    """Extract a single trace's conversation from traces.jsonl."""
    conn = duckdb.connect()

    if trace_id:
        # Explicit trace-id: include everything
        where_clause = f"AND span.traceId LIKE '{trace_id}%'"
    else:
        # No trace-id: only agent sessions (exclude NES, inline completions, suggestions)
        # First find trace IDs that contain an invoke_agent span
        agent_ids = conn.execute(f"""
            WITH spans AS (
                SELECT unnest(rs.scopeSpans) AS ss
                FROM (SELECT unnest(resourceSpans) AS rs FROM read_json('{DATA_DIR}/traces.jsonl'))
            ),
            flat AS (
                SELECT unnest(ss.spans) AS span FROM spans
            )
            SELECT DISTINCT span.traceId
            FROM flat
            WHERE span.name LIKE '%invoke_agent%'
        """).fetchall()
        if not agent_ids:
            return {}
        id_list = ",".join(f"'{r[0]}'" for r in agent_ids)
        where_clause = f"AND span.traceId IN ({id_list})"

    rows = conn.execute(f"""
        WITH spans AS (
            SELECT unnest(rs.scopeSpans) AS ss, rs.resource.attributes AS res_attrs
            FROM (SELECT unnest(resourceSpans) AS rs FROM read_json('{DATA_DIR}/traces.jsonl'))
        ),
        flat AS (
            SELECT
                list_filter(res_attrs, x -> x.key = 'service.name')[1].value.stringValue AS agent,
                unnest(ss.spans) AS span
            FROM spans
        )
        SELECT
            span.traceId,
            agent,
            span.name,
            list_filter(span.attributes, x -> x.key = 'gen_ai.request.model')[1].value.stringValue AS model,
            list_filter(span.attributes, x -> x.key = 'gen_ai.input.messages')[1].value.stringValue AS input_msg,
            list_filter(span.attributes, x -> x.key = 'gen_ai.output.messages')[1].value.stringValue AS output_msg,
            list_filter(span.attributes, x -> x.key = 'gen_ai.tool.name')[1].value.stringValue AS tool_name,
            list_filter(span.attributes, x -> x.key = 'gen_ai.operation.name')[1].value.stringValue AS op_name,
            CAST(span.startTimeUnixNano AS BIGINT) AS start_ns
        FROM flat
        WHERE span.traceId IS NOT NULL {where_clause}
        ORDER BY start_ns DESC
        LIMIT 50
    """).fetchall()

    if not rows:
        return {}

    # Use the first trace_id found
    target_id = rows[0][0]
    trace_rows = [r for r in rows if r[0] == target_id]

    conversation = []
    for row in sorted(trace_rows, key=lambda r: r[8]):  # sort by start_ns
        _, agent, name, model, input_msg, output_msg, tool_name, op_name, _ = row
        entry = {"agent": agent, "span": name, "model": model, "operation": op_name}
        if tool_name:
            entry["tool"] = tool_name
        if input_msg:
            # Truncate long messages for the judge
            entry["input"] = (
                input_msg[:2000] + "..." if len(input_msg or "") > 2000 else input_msg
            )
        if output_msg:
            entry["output"] = (
                output_msg[:2000] + "..."
                if len(output_msg or "") > 2000
                else output_msg
            )
        conversation.append(entry)

    return {
        "trace_id": target_id,
        "agent": trace_rows[0][1],
        "spans": len(trace_rows),
        "conversation": conversation,
        "first_prompt": _extract_first_prompt(conversation),
    }


def _extract_first_prompt(conversation: list[dict]) -> str:
    """Extract the user's first prompt text from the conversation."""
    for entry in conversation:
        input_msg = entry.get("input", "")
        if not input_msg:
            continue
        try:
            messages = json.loads(input_msg)
            for msg in messages:
                if msg.get("role") == "user":
                    for part in msg.get("parts", []):
                        if (
                            part.get("type") == "text"
                            and part.get("content", "").strip()
                        ):
                            text = part["content"].strip()
                            return text[:120] + "..." if len(text) > 120 else text
        except (json.JSONDecodeError, TypeError, KeyError):
            continue
    return "(no user prompt found)"


def build_prompt(trace_data: dict) -> str:
    # Only include spans that have meaningful content
    meaningful = [
        c
        for c in trace_data["conversation"]
        if c.get("input") or c.get("output") or c.get("tool")
    ]

    # Further truncate to keep prompt manageable
    summary_items = meaningful[:15]

    conversation_json = json.dumps(summary_items, ensure_ascii=False, indent=2)

    return textwrap.dedent(f"""\
        Evaluate this AI agent interaction trace. Return ONLY a JSON object with scores.

        Agent: {trace_data["agent"]}
        Trace ID: {trace_data["trace_id"][:16]}
        Spans: {trace_data["spans"]}

        Conversation (truncated):
        {conversation_json}

        Score each dimension 1-5 and provide a one-line reason:

        {{
          "autonomy": {{"score": <1-5>, "reason": "<did the agent complete tasks without human correction?>"}},
          "efficiency": {{"score": <1-5>, "reason": "<were tool calls and tokens used efficiently?>"}},
          "direction_needed": {{"score": <1-5, 1=no direction needed, 5=heavy direction>, "reason": "<how much did the human need to guide/correct?>"}},
          "security": {{"risk": "<low|medium|high>", "reason": "<any suspicious file access, commands, or data exposure?>"}},
          "summary": "<one sentence summary of this interaction>"
        }}
    """)


async def run_copilot(prompt: str) -> str:
    """Score using Copilot SDK (tools disabled, no OTel)."""
    from copilot import CopilotClient, SubprocessConfig
    from copilot.session import PermissionHandler

    response_text = ""
    done = asyncio.Event()

    def on_event(event):
        nonlocal response_text
        if event.type.value == "assistant.message":
            response_text = event.data.content
        elif event.type.value == "session.idle":
            done.set()

    async with CopilotClient(
        SubprocessConfig(
            env={"COPILOT_OTEL_ENABLED": "false"},
        )
    ) as client:
        async with await client.create_session(
            on_permission_request=PermissionHandler.deny_all
            if hasattr(PermissionHandler, "deny_all")
            else lambda req, inv: __import__(
                "copilot.session", fromlist=["PermissionRequestResult"]
            ).PermissionRequestResult(kind="denied-by-rules"),
            model="gpt-4o-mini",
            infinite_sessions={"enabled": False},
        ) as session:
            session.on(on_event)
            await session.send(prompt)
            await asyncio.wait_for(done.wait(), timeout=120)

    return response_text


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Score a trace using Copilot SDK as LLM-as-Judge"
    )
    parser.add_argument("--trace-id", help="Trace ID prefix to score")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print prompt without calling copilot"
    )
    args = parser.parse_args()

    if not (DATA_DIR / "traces.jsonl").exists():
        print("No traces.jsonl found.", file=sys.stderr)
        sys.exit(1)

    print("Extracting trace...", file=sys.stderr)
    trace_data = extract_trace(args.trace_id)
    if not trace_data:
        print("No matching traces found.", file=sys.stderr)
        sys.exit(1)

    print(
        f"Trace: {trace_data['trace_id'][:16]}... ({trace_data['spans']} spans, agent: {trace_data['agent']})",
        file=sys.stderr,
    )
    print(f"Prompt: {trace_data['first_prompt']}", file=sys.stderr)

    prompt = build_prompt(trace_data)

    if args.dry_run:
        print("\n=== Prompt (dry-run) ===\n")
        print(prompt)
        return

    print("Scoring with Copilot SDK (tools disabled, no OTel)...", file=sys.stderr)
    result = asyncio.run(run_copilot(prompt))
    print("\n=== Score Result ===\n")
    print(result)


if __name__ == "__main__":
    main()
