#!/usr/bin/env python3
"""Ask the local Venture Metrics agent a question."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from venture_metrics_agent.app.config import DEFAULT_DB_PATH
from venture_metrics_agent.retrieval.agent import QueryOptions, answer_question


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="+", help="Question to ask.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path.")
    parser.add_argument("--top-k", type=int, default=8, help="Number of chunks to retrieve.")
    args = parser.parse_args()

    response = answer_question(
        args.db,
        " ".join(args.question),
        options=QueryOptions(top_k=args.top_k),
    )
    print(json.dumps(response, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
