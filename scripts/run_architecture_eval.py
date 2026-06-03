#!/usr/bin/env python3
"""Run architecture comparison evaluation and optionally write a report bundle."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from venture_metrics_agent.app.config import DEFAULT_DB_PATH, PROJECT_ROOT
from venture_metrics_agent.evaluation.runner import EvalOptions, eval_cases_from_json, run_architecture_eval


def default_output_dir() -> Path:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return PROJECT_ROOT / "reports" / "evaluations" / "runs" / run_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path.")
    parser.add_argument("--cases", help="Optional JSON file of eval cases.")
    parser.add_argument("--architecture", "-a", action="append", help="Architecture id. Repeat to compare multiple.")
    parser.add_argument("--top-k", type=int, default=8, help="Number of internal results per search.")
    parser.add_argument("--no-web", action="store_true", help="Disable web fallback/search.")
    parser.add_argument("--with-llm", action="store_true", help="Allow configured LLM calls during eval.")
    parser.add_argument("--rag-threshold", type=float, default=0.65, help="Minimum pass score for each RAG dimension.")
    parser.add_argument("--quiet", action="store_true", help="Do not print the full JSON report to stdout.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for the evaluation report bundle.",
    )
    args = parser.parse_args()
    output_dir = Path(args.output_dir) if args.output_dir else default_output_dir()

    cases = eval_cases_from_json(args.cases) if args.cases else None
    report = run_architecture_eval(
        args.db,
        cases=cases,
        options=EvalOptions(
            top_k=args.top_k,
            use_web_fallback=not args.no_web,
            architectures=args.architecture or ["deterministic_controller", "coverage_rag", "plan_execute", "react_loop"],
            output_dir=output_dir,
            no_llm=not args.with_llm,
            rag_threshold=args.rag_threshold,
        ),
    )
    _write_latest_pointer(output_dir)
    if args.quiet:
        print(f"Wrote evaluation report to {output_dir}")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))


def _write_latest_pointer(output_dir: Path) -> None:
    pointer = PROJECT_ROOT / "reports" / "evaluations" / "LATEST_RUN.txt"
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(str(output_dir.relative_to(PROJECT_ROOT)) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
