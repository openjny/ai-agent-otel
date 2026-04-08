#!/usr/bin/env python3
"""DuckDB-based analysis for AI agent OTel telemetry.

Usage:
    # Summary of all agents
    uv run scripts/analyze.py summary

    # Tool call ranking
    uv run scripts/analyze.py tools

    # Cost estimate
    uv run scripts/analyze.py cost

    # Security audit
    uv run scripts/analyze.py security

    # Direction/intervention analysis
    uv run scripts/analyze.py direction
"""
# /// script
# requires-python = ">=3.11"
# dependencies = ["duckdb", "pandas"]
# ///

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

DATA_DIR = Path(__file__).parent.parent / "data"

# Pricing per 1M tokens (USD): (input, output)
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4.6-1m": (15.0, 75.0),
    "claude-opus-4.6": (15.0, 75.0),
    "claude-sonnet-4.6": (3.0, 15.0),
    "claude-sonnet-4.5": (3.0, 15.0),
    "claude-haiku-4.5": (0.80, 4.0),
    "gpt-5.1": (2.0, 8.0),
    "gpt-5": (2.0, 8.0),
    "gpt-5-mini": (0.40, 1.60),
    "gpt-4o": (2.50, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.0, 8.0),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
}


def _lookup_price(model: str) -> tuple[float, float]:
    if not model:
        return (0.0, 0.0)
    for pattern, price in MODEL_PRICING.items():
        if pattern in model:
            return price
    return (0.0, 0.0)


def get_conn() -> duckdb.DuckDBPyConnection:
    return duckdb.connect()


def traces_exist() -> bool:
    return (DATA_DIR / "traces.jsonl").exists()


def cmd_summary(conn: duckdb.DuckDBPyConnection) -> None:
    """Show summary stats across all agents."""
    print("=== Agent Summary ===\n")
    conn.execute(f"""
        WITH spans AS (
            SELECT
                unnest(rs.scopeSpans) AS ss,
                rs.resource.attributes AS res_attrs
            FROM (
                SELECT unnest(resourceSpans) AS rs
                FROM read_json('{DATA_DIR}/traces.jsonl')
            )
        ),
        flat AS (
            SELECT
                list_filter(res_attrs, x -> x.key = 'service.name')[1].value.stringValue AS agent,
                unnest(ss.spans) AS span
            FROM spans
        )
        SELECT
            COALESCE(agent, 'unknown') AS agent,
            COUNT(*) AS total_spans,
            COUNT(DISTINCT span.traceId) AS traces,
            MIN(to_timestamp(CAST(span.startTimeUnixNano AS BIGINT) / 1000000000)) AS first_seen,
            MAX(to_timestamp(CAST(span.startTimeUnixNano AS BIGINT) / 1000000000)) AS last_seen
        FROM flat
        GROUP BY agent
        ORDER BY total_spans DESC
    """)
    print(conn.fetchdf().to_string(index=False))


def cmd_tools(conn: duckdb.DuckDBPyConnection) -> None:
    """Show tool call ranking per agent."""
    print("=== Tool Call Ranking ===\n")
    conn.execute(f"""
        WITH spans AS (
            SELECT
                unnest(rs.scopeSpans) AS ss,
                rs.resource.attributes AS res_attrs
            FROM (
                SELECT unnest(resourceSpans) AS rs
                FROM read_json('{DATA_DIR}/traces.jsonl')
            )
        ),
        flat AS (
            SELECT
                list_filter(res_attrs, x -> x.key = 'service.name')[1].value.stringValue AS agent,
                unnest(ss.spans) AS span
            FROM spans
        ),
        tool_spans AS (
            SELECT
                agent,
                list_filter(span.attributes, x -> x.key = 'gen_ai.tool.name')[1].value.stringValue AS tool_name,
                (CAST(span.endTimeUnixNano AS BIGINT) - CAST(span.startTimeUnixNano AS BIGINT)) / 1000000 AS duration_ms
            FROM flat
            WHERE span.name LIKE '%execute_tool%'
               OR list_filter(span.attributes, x -> x.key = 'gen_ai.operation.name')[1].value.stringValue = 'execute_tool'
        )
        SELECT
            COALESCE(agent, 'unknown') AS agent,
            COALESCE(tool_name, 'unknown') AS tool,
            COUNT(*) AS calls,
            ROUND(AVG(duration_ms)) AS avg_ms,
            ROUND(MAX(duration_ms)) AS max_ms
        FROM tool_spans
        WHERE tool_name IS NOT NULL
        GROUP BY agent, tool_name
        ORDER BY calls DESC
        LIMIT 30
    """)
    print(conn.fetchdf().to_string(index=False))


def cmd_cost(conn: duckdb.DuckDBPyConnection) -> None:
    """Estimate token costs per agent with USD pricing."""
    print("=== Cost Estimate ===\n")
    conn.execute(f"""
        WITH spans AS (
            SELECT
                unnest(rs.scopeSpans) AS ss,
                rs.resource.attributes AS res_attrs
            FROM (
                SELECT unnest(resourceSpans) AS rs
                FROM read_json('{DATA_DIR}/traces.jsonl')
            )
        ),
        flat AS (
            SELECT
                list_filter(res_attrs, x -> x.key = 'service.name')[1].value.stringValue AS agent,
                unnest(ss.spans) AS span
            FROM spans
        ),
        token_spans AS (
            SELECT
                agent,
                list_filter(span.attributes, x -> x.key = 'gen_ai.request.model')[1].value.stringValue AS model,
                COALESCE(CAST(list_filter(span.attributes, x -> x.key = 'gen_ai.usage.input_tokens')[1].value.intValue AS BIGINT), 0) AS input_tokens,
                COALESCE(CAST(list_filter(span.attributes, x -> x.key = 'gen_ai.usage.output_tokens')[1].value.intValue AS BIGINT), 0) AS output_tokens
            FROM flat
            WHERE list_filter(span.attributes, x -> x.key = 'gen_ai.operation.name')[1].value.stringValue = 'chat'
        )
        SELECT
            COALESCE(agent, 'unknown') AS agent,
            COALESCE(model, 'unknown') AS model,
            COUNT(*) AS llm_calls,
            SUM(input_tokens) AS total_input,
            SUM(output_tokens) AS total_output
        FROM token_spans
        GROUP BY agent, model
        ORDER BY (SUM(input_tokens) + SUM(output_tokens)) DESC
    """)
    df = conn.fetchdf()

    df["input_cost"] = df.apply(
        lambda r: r["total_input"] / 1_000_000 * _lookup_price(r["model"])[0], axis=1
    )
    df["output_cost"] = df.apply(
        lambda r: r["total_output"] / 1_000_000 * _lookup_price(r["model"])[1], axis=1
    )
    df["total_usd"] = df["input_cost"] + df["output_cost"]

    df["input_cost"] = df["input_cost"].map("${:.4f}".format)
    df["output_cost"] = df["output_cost"].map("${:.4f}".format)
    df["total_usd"] = df["total_usd"].map("${:.4f}".format)

    print(df.to_string(index=False))

    grand = df["total_usd"].str.replace("$", "", regex=False).astype(float).sum()
    print(f"\n{'─' * 50}")
    print(f"Grand Total: ${grand:.4f}")

    unknown_models = df[
        df.apply(lambda r: _lookup_price(r["model"]) == (0.0, 0.0), axis=1)
    ]
    if not unknown_models.empty:
        names = ", ".join(unknown_models["model"].unique())
        print(
            f"\nWarning: No pricing for: {names} (showing $0). Update MODEL_PRICING in analyze.py."
        )


def cmd_security(conn: duckdb.DuckDBPyConnection) -> None:
    """Scan for suspicious tool calls."""
    print("=== Security Audit ===\n")

    # Check traces for dangerous patterns
    conn.execute(f"""
        WITH spans AS (
            SELECT
                unnest(rs.scopeSpans) AS ss,
                rs.resource.attributes AS res_attrs
            FROM (
                SELECT unnest(resourceSpans) AS rs
                FROM read_json('{DATA_DIR}/traces.jsonl')
            )
        ),
        flat AS (
            SELECT
                list_filter(res_attrs, x -> x.key = 'service.name')[1].value.stringValue AS agent,
                unnest(ss.spans) AS span
            FROM spans
        )
        SELECT
            COALESCE(agent, 'unknown') AS agent,
            span.name AS span_name,
            span.traceId AS trace_id,
            to_timestamp(CAST(span.startTimeUnixNano AS BIGINT) / 1000000000) AS timestamp,
            'dangerous_command' AS alert_type
        FROM flat
        WHERE (
            -- Check span attributes for dangerous patterns
            EXISTS (
                SELECT 1 FROM unnest(span.attributes) a
                WHERE a.key IN ('tool_input', 'gen_ai.tool.name')
                  AND (
                    a.value.stringValue ILIKE '%rm -rf%'
                    OR a.value.stringValue ILIKE '%sudo %'
                    OR a.value.stringValue ILIKE '%chmod 777%'
                    OR a.value.stringValue ILIKE '%.env%'
                    OR a.value.stringValue ILIKE '%/credentials%'
                    OR a.value.stringValue ILIKE '%/.ssh/%'
                    OR a.value.stringValue ILIKE '%/.aws/%'
                  )
            )
        )
        ORDER BY timestamp DESC
        LIMIT 50
    """)
    results = conn.fetchdf()
    if results.empty:
        print("No suspicious patterns found.")
    else:
        print(results.to_string(index=False))


def cmd_direction(conn: duckdb.DuckDBPyConnection) -> None:
    """Analyze user direction/intervention patterns (requires content capture)."""
    logs_path = DATA_DIR / "logs.jsonl"
    if not logs_path.exists():
        print(
            "No logs.jsonl found. Content capture may not be enabled.", file=sys.stderr
        )
        return

    print("=== Direction Analysis ===\n")
    print("Searching for correction patterns in user messages...\n")

    conn.execute(f"""
        WITH log_entries AS (
            SELECT
                unnest(resourceLogs) AS rl
            FROM read_json('{logs_path}')
        ),
        flat_logs AS (
            SELECT
                list_filter(rl.resource.attributes, x -> x.key = 'service.name')[1].value.stringValue AS agent,
                unnest(rl.scopeLogs) AS sl
            FROM log_entries
        ),
        log_records AS (
            SELECT
                agent,
                unnest(sl.logRecords) AS lr
            FROM flat_logs
        )
        SELECT
            COALESCE(agent, 'unknown') AS agent,
            COUNT(*) AS total_events,
            COUNT(CASE WHEN
                lr.body.stringValue ILIKE '%no,%'
                OR lr.body.stringValue ILIKE '%wrong%'
                OR lr.body.stringValue ILIKE '%instead%'
                OR lr.body.stringValue ILIKE '%try again%'
                OR lr.body.stringValue ILIKE '%not what%'
                OR lr.body.stringValue ILIKE '%やり直%'
                OR lr.body.stringValue ILIKE '%違う%'
            THEN 1 END) AS correction_signals
        FROM log_records
        GROUP BY agent
        ORDER BY agent
    """)
    print(conn.fetchdf().to_string(index=False))
    print(
        "\nNote: Keyword-based detection is approximate. Use 'copilot -p' for LLM-as-Judge scoring."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze AI agent OTel telemetry with DuckDB"
    )
    parser.add_argument(
        "command",
        choices=["summary", "tools", "cost", "security", "direction"],
        help="Analysis command to run",
    )
    args = parser.parse_args()

    if not traces_exist():
        print(
            f"Error: {DATA_DIR}/traces.jsonl not found. Collect some telemetry first.",
            file=sys.stderr,
        )
        sys.exit(1)

    conn = get_conn()
    commands = {
        "summary": cmd_summary,
        "tools": cmd_tools,
        "cost": cmd_cost,
        "security": cmd_security,
        "direction": cmd_direction,
    }
    commands[args.command](conn)


if __name__ == "__main__":
    main()
