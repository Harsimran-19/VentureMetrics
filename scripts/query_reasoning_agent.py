#!/usr/bin/env python3
"""Ask the experimental reasoning-style Venture Metrics agent a question."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from venture_metrics_agent.app.config import DEFAULT_DB_PATH
from venture_metrics_agent.llm.provider import LLMConfig, LLMProvider
from venture_metrics_agent.reasoning import ReasoningOptions, answer_question_reasoning


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="+", help="Question to ask.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path.")
    parser.add_argument("--top-k", type=int, default=8, help="Number of internal corpus results to inspect.")
    parser.add_argument("--no-web", action="store_true", help="Disable controlled web-search tool use.")
    parser.add_argument("--no-remember-web", action="store_true", help="Do not store controlled web results for reuse.")
    parser.add_argument("--no-llm", action="store_true", help="Use extractive synthesis even if .env has an LLM key.")
    args = parser.parse_args()

    llm = LLMProvider(LLMConfig(api_key=None)) if args.no_llm else None
    response = answer_question_reasoning(
        args.db,
        " ".join(args.question),
        options=ReasoningOptions(
            top_k=args.top_k,
            use_web_fallback=not args.no_web,
            remember_web_results=not args.no_remember_web,
        ),
        llm=llm,
    )
    print(json.dumps(response, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
