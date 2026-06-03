from __future__ import annotations

from pathlib import Path

from venture_metrics_agent.evaluation.runner import DEFAULT_CASES, EvalCase, EvalOptions, run_architecture_eval
from venture_metrics_agent.ingestion.source_registry import init_db


def test_architecture_eval_runs_and_summarizes(tmp_path: Path) -> None:
    db_path = tmp_path / "eval.db"
    conn = init_db(db_path)
    conn.close()

    report = run_architecture_eval(
        db_path,
        cases=[
            EvalCase(
                id="casual_hi",
                question="hi",
                category="casual",
                expected_intent="casual_chat",
                expect_web=False,
            )
        ],
        options=EvalOptions(
            architectures=["deterministic_controller", "coverage_rag"],
            use_web_fallback=False,
            output_dir=tmp_path / "report",
        ),
    )

    assert report["summary"]["architecture_count"] == 2
    assert len(report["results"]) == 2
    assert (tmp_path / "report" / "summary.md").exists()
    assert (tmp_path / "report" / "summary.json").exists()
    assert (tmp_path / "report" / "architecture_scorecard.csv").exists()


def test_default_architecture_eval_dataset_has_20_cases() -> None:
    assert len(DEFAULT_CASES) == 20
    assert len({case.id for case in DEFAULT_CASES}) == 20
