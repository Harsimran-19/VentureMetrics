from pathlib import Path

from venture_metrics_agent.ingestion.source_registry import init_db
from venture_metrics_agent.reasoning.eval_runner import EvalCase, EvalOptions, run_eval_suite


def test_eval_runner_scores_no_tool_case_on_temp_db(tmp_path: Path) -> None:
    db_path = tmp_path / "eval.db"
    conn = init_db(db_path)
    conn.close()

    report = run_eval_suite(
        db_path,
        cases=[
            EvalCase(
                id="hi",
                question="hi",
                expected_intent="casual_chat",
                expected_source_mode="no_tools",
                expect_web_used=False,
                max_citations=0,
            )
        ],
        options=EvalOptions(include_legacy=False),
    )

    assert report["summary"]["total"] == 1
    assert report["summary"]["passed"] == 1
    assert report["results"][0]["passed"] is True
    assert report["results"][0]["reasoning"]["intent"] == "casual_chat"
