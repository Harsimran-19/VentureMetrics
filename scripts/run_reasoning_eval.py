#!/usr/bin/env python3
"""Run the reasoning evaluation suite against a temporary database copy."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from venture_metrics_agent.app.config import DEFAULT_DB_PATH
from venture_metrics_agent.observability import record_eval_report
from venture_metrics_agent.reasoning.eval_runner import EvalOptions, eval_cases_from_json, run_eval_suite


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path.")
    parser.add_argument("--cases", help="Optional JSON file containing eval case objects.")
    parser.add_argument("--top-k", type=int, default=8, help="Number of internal results per search.")
    parser.add_argument("--real-web", action="store_true", help="Use configured real web search instead of simulated web.")
    parser.add_argument("--no-web", action="store_true", help="Disable web fallback/search.")
    parser.add_argument("--no-legacy", action="store_true", help="Skip legacy agent comparison.")
    parser.add_argument("--record", action="store_true", help="Store the scored eval report in the observability DB.")
    parser.add_argument("--output", help="Optional path to write full JSON results.")
    args = parser.parse_args()

    cases = eval_cases_from_json(args.cases) if args.cases else None
    report = run_eval_suite(
        args.db,
        cases=cases,
        options=EvalOptions(
            top_k=args.top_k,
            use_web_fallback=not args.no_web,
            simulate_web=not args.real_web,
            include_legacy=not args.no_legacy,
        ),
    )

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.record:
        record = record_eval_report(
            args.db,
            report,
            name="reasoning_eval",
            agent_name="reasoning_agent",
            config={
                "top_k": args.top_k,
                "use_web_fallback": not args.no_web,
                "simulate_web": not args.real_web,
                "include_legacy": not args.no_legacy,
                "cases": args.cases,
            },
        )
        report["recorded_eval_run_id"] = record.eval_run_id
        report["recorded_eval_result_count"] = record.eval_result_count
        text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)


if __name__ == "__main__":
    main()
