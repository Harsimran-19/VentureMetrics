#!/usr/bin/env python3
"""Run one Venture Metrics architecture adapter for a question."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from venture_metrics_agent.app.config import DEFAULT_DB_PATH
from venture_metrics_agent.architectures import ArchitectureOptions, list_architectures, run_architectures
from venture_metrics_agent.llm.provider import LLMConfig, LLMProvider


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="*", help="Question to ask.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path.")
    parser.add_argument("--architecture", "-a", action="append", help="Architecture id. Repeat to compare multiple.")
    parser.add_argument("--list", action="store_true", help="List available architectures and exit.")
    parser.add_argument("--top-k", type=int, default=8, help="Number of internal results per search.")
    parser.add_argument("--no-web", action="store_true", help="Disable web fallback/search.")
    parser.add_argument("--no-llm", action="store_true", help="Use non-LLM extractive/safe fallback paths.")
    args = parser.parse_args()

    if args.list:
        print(json.dumps(list_architectures(), ensure_ascii=False, indent=2))
        return
    if not args.question:
        parser.error("question is required unless --list is used")

    llm = LLMProvider(LLMConfig(api_key=None)) if args.no_llm else None
    outputs = run_architectures(
        args.architecture or ["deterministic_controller"],
        args.db,
        " ".join(args.question),
        options=ArchitectureOptions(top_k=args.top_k, use_web_fallback=not args.no_web),
        llm=llm,
    )
    print(json.dumps({"results": outputs}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
