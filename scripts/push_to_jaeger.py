#!/usr/bin/env python3
"""Push specific traces from JSON Lines file to Jaeger for visualization.

Usage:
    # Push a specific trace by ID
    uv run scripts/push_to_jaeger.py --trace-id abc123def456

    # Push the N most recent traces
    uv run scripts/push_to_jaeger.py --recent 5

    # Push traces matching a filter
    uv run scripts/push_to_jaeger.py --filter 'invoke_agent'
"""
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

DEFAULT_TRACES_FILE = Path(__file__).parent.parent / "data" / "traces.jsonl"
DEFAULT_JAEGER_ENDPOINT = "http://localhost:4328/v1/traces"


def load_resource_spans(path: Path) -> list[dict]:
    """Load all resource spans from a JSON Lines file."""
    resource_spans: list[dict] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            for rs in data.get("resourceSpans", []):
                resource_spans.append(rs)
    return resource_spans


def extract_trace_ids(rs: dict) -> set[str]:
    """Extract all trace IDs from a resource span."""
    ids: set[str] = set()
    for ss in rs.get("scopeSpans", []):
        for span in ss.get("spans", []):
            tid = span.get("traceId", "")
            if tid:
                ids.add(tid)
    return ids


def filter_by_trace_id(resource_spans: list[dict], trace_id: str) -> list[dict]:
    """Filter resource spans to those containing a specific trace ID."""
    matched: list[dict] = []
    for rs in resource_spans:
        filtered_scope_spans = []
        for ss in rs.get("scopeSpans", []):
            filtered_spans = [
                s for s in ss.get("spans", [])
                if s.get("traceId", "").startswith(trace_id)
            ]
            if filtered_spans:
                filtered_scope_spans.append({**ss, "spans": filtered_spans})
        if filtered_scope_spans:
            matched.append({**rs, "scopeSpans": filtered_scope_spans})
    return matched


def filter_by_span_name(resource_spans: list[dict], pattern: str) -> list[dict]:
    """Filter resource spans to those with span names containing pattern."""
    matched: list[dict] = []
    for rs in resource_spans:
        filtered_scope_spans = []
        for ss in rs.get("scopeSpans", []):
            filtered_spans = [
                s for s in ss.get("spans", [])
                if pattern.lower() in s.get("name", "").lower()
            ]
            if filtered_spans:
                filtered_scope_spans.append({**ss, "spans": filtered_spans})
        if filtered_scope_spans:
            matched.append({**rs, "scopeSpans": filtered_scope_spans})
    return matched


def get_recent_trace_ids(resource_spans: list[dict], n: int) -> list[str]:
    """Get the N most recent unique trace IDs by start time."""
    traces: dict[str, int] = {}
    for rs in resource_spans:
        for ss in rs.get("scopeSpans", []):
            for span in ss.get("spans", []):
                tid = span.get("traceId", "")
                start = int(span.get("startTimeUnixNano", "0"))
                if tid and (tid not in traces or start > traces[tid]):
                    traces[tid] = start
    sorted_ids = sorted(traces, key=lambda t: traces[t], reverse=True)
    return sorted_ids[:n]


def push_to_jaeger(resource_spans: list[dict], endpoint: str) -> None:
    """POST resource spans to Jaeger's OTLP endpoint."""
    payload = {"resourceSpans": resource_spans}
    resp = httpx.post(endpoint, json=payload, timeout=10)
    resp.raise_for_status()
    span_count = sum(
        len(s.get("spans", []))
        for rs in resource_spans
        for s in rs.get("scopeSpans", [])
    )
    print(f"Pushed {span_count} spans to {endpoint}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Push traces to Jaeger for visualization")
    parser.add_argument("--file", type=Path, default=DEFAULT_TRACES_FILE, help="Path to traces.jsonl")
    parser.add_argument("--endpoint", default=DEFAULT_JAEGER_ENDPOINT, help="Jaeger OTLP HTTP endpoint")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--trace-id", help="Push a specific trace by ID (prefix match)")
    group.add_argument("--recent", type=int, metavar="N", help="Push the N most recent traces")
    group.add_argument("--filter", metavar="PATTERN", help="Push traces with span names matching pattern")

    args = parser.parse_args()

    if not args.file.exists():
        print(f"Error: {args.file} not found", file=sys.stderr)
        sys.exit(1)

    resource_spans = load_resource_spans(args.file)
    if not resource_spans:
        print("No spans found in file", file=sys.stderr)
        sys.exit(1)

    if args.trace_id:
        filtered = filter_by_trace_id(resource_spans, args.trace_id)
    elif args.recent:
        trace_ids = get_recent_trace_ids(resource_spans, args.recent)
        print(f"Found {len(trace_ids)} recent traces: {', '.join(t[:12] + '...' for t in trace_ids)}")
        filtered = []
        for tid in trace_ids:
            filtered.extend(filter_by_trace_id(resource_spans, tid))
    else:
        filtered = filter_by_span_name(resource_spans, args.filter)
        trace_ids_found = set()
        for rs in filtered:
            trace_ids_found.update(extract_trace_ids(rs))
        # Expand to include all spans for matched traces
        filtered = []
        for tid in trace_ids_found:
            filtered.extend(filter_by_trace_id(resource_spans, tid))

    if not filtered:
        print("No matching traces found", file=sys.stderr)
        sys.exit(1)

    push_to_jaeger(filtered, args.endpoint)
    print(f"View at: http://localhost:16686")


if __name__ == "__main__":
    main()
