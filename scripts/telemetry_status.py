#!/usr/bin/env python3
"""Show local observability counts and recent agent runs."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from venture_metrics_agent.app.config import DEFAULT_DB_PATH
from venture_metrics_agent.observability import init_observability_db, langfuse_status


TRACKED_TABLES = (
    "chat_sessions",
    "chat_messages",
    "agent_runs",
    "agent_run_steps",
    "retrieval_events",
    "retrieval_event_results",
    "answer_citations",
    "user_feedback",
    "eval_cases",
    "eval_runs",
    "eval_results",
    "query_logs",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path.")
    parser.add_argument("--limit", type=int, default=5, help="Recent runs to show.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a text report.")
    args = parser.parse_args()

    conn = init_observability_db(args.db)
    try:
        report = {
            "database": str(Path(args.db)),
            "langfuse": langfuse_status(),
            "counts": {table: _count(conn, table) for table in TRACKED_TABLES},
            "recent_runs": _recent_runs(conn, limit=args.limit),
        }
    finally:
        conn.close()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_text_report(report)


def _count(conn: sqlite3.Connection, table_name: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
    return int(row[0])


def _recent_runs(conn: sqlite3.Connection, *, limit: int) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT
            id,
            agent_name,
            confidence,
            source_mode,
            used_web_fallback,
            substr(question, 1, 120),
            created_at
        FROM agent_runs
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        {
            "id": int(row[0]),
            "agent_name": row[1],
            "confidence": row[2],
            "source_mode": row[3],
            "used_web_fallback": bool(row[4]),
            "question": row[5],
            "created_at": row[6],
        }
        for row in rows
    ]


def _print_text_report(report: dict[str, object]) -> None:
    print(f"Database: {report['database']}")
    langfuse = report["langfuse"]
    assert isinstance(langfuse, dict)
    print(
        "\nLangfuse:"
        f" enabled={langfuse['enabled']}"
        f" configured={langfuse['configured']}"
        f" sdk_installed={langfuse['sdk_installed']}"
        f" base_url={langfuse['base_url']}"
    )
    print("\nTelemetry counts:")
    counts = report["counts"]
    assert isinstance(counts, dict)
    for table, count in counts.items():
        print(f"  {table}: {count}")

    print("\nRecent runs:")
    recent_runs = report["recent_runs"]
    assert isinstance(recent_runs, list)
    if not recent_runs:
        print("  No agent runs logged yet.")
        return
    for run in recent_runs:
        print(
            "  "
            f"#{run['id']} {run['agent_name']} "
            f"{run['confidence']} {run['source_mode']} "
            f"web={run['used_web_fallback']} "
            f"- {run['question']}"
        )


if __name__ == "__main__":
    main()
