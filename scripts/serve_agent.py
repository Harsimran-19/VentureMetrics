#!/usr/bin/env python3
"""Run the local Venture Metrics web UI."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from venture_metrics_agent.app.config import DEFAULT_DB_PATH
from venture_metrics_agent.ui.local_server import run_server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"), help="Host to bind.")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")), help="Port to bind.")
    parser.add_argument(
        "--db",
        default=os.environ.get("DB_PATH", str(DEFAULT_DB_PATH)),
        help="SQLite database path.",
    )
    args = parser.parse_args()
    run_server(host=args.host, port=args.port, db_path=args.db)


if __name__ == "__main__":
    main()
