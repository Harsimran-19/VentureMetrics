#!/usr/bin/env python3
"""Compare the legacy linear agent with the reasoning controller."""

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
from venture_metrics_agent.retrieval.agent import QueryOptions, answer_question
from venture_metrics_agent.reasoning import ReasoningOptions, answer_question_reasoning


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="+", help="Question to ask both agents.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path.")
    parser.add_argument("--top-k", type=int, default=8, help="Number of internal results.")
    parser.add_argument("--no-web", action="store_true", help="Disable web fallback/search in both agents.")
    parser.add_argument("--no-remember-web", action="store_true", help="Do not let the reasoning path store web results.")
    parser.add_argument("--no-llm", action="store_true", help="Use extractive synthesis for both agents.")
    args = parser.parse_args()

    question = " ".join(args.question)
    llm = LLMProvider(LLMConfig(api_key=None)) if args.no_llm else None
    legacy = answer_question(
        args.db,
        question,
        options=QueryOptions(top_k=args.top_k, use_web_fallback=not args.no_web),
        llm=llm,
    )
    reasoning = answer_question_reasoning(
        args.db,
        question,
        options=ReasoningOptions(
            top_k=args.top_k,
            use_web_fallback=not args.no_web,
            remember_web_results=not args.no_remember_web,
        ),
        llm=llm,
    )
    output = {
        "question": question,
        "summary": {
            "legacy": _summary(legacy),
            "reasoning": _summary(reasoning),
        },
        "legacy": legacy,
        "reasoning": reasoning,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def _summary(response: dict[str, object]) -> dict[str, object]:
    trace = response.get("reasoning_trace") or []
    return {
        "confidence": response.get("confidence"),
        "source_mode": response.get("source_mode"),
        "used_web_fallback": response.get("used_web_fallback"),
        "citation_count": len(response.get("citations") or []),
        "tool_decisions": [step.get("decision") for step in trace if isinstance(step, dict)],
    }


if __name__ == "__main__":
    main()
