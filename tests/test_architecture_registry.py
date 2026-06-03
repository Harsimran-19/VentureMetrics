from __future__ import annotations

from pathlib import Path

from venture_metrics_agent.architectures import ArchitectureOptions, list_architectures, run_architecture
from venture_metrics_agent.ingestion.source_registry import init_db
from venture_metrics_agent.llm.provider import LLMConfig, LLMProvider


def test_architecture_registry_lists_expected_adapters() -> None:
    ids = {item["id"] for item in list_architectures()}

    assert "linear_rag" in ids
    assert "deterministic_controller" in ids
    assert "coverage_rag" in ids
    assert "plan_execute" in ids
    assert "react_loop" in ids
    assert "cag_pack" in ids
    assert "rlm_experiment" in ids


def test_architecture_adapter_returns_common_contract(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.db"
    conn = init_db(db_path)
    conn.close()

    response = run_architecture(
        "deterministic_controller",
        db_path,
        "hi",
        options=ArchitectureOptions(use_web_fallback=False),
        llm=LLMProvider(LLMConfig(api_key=None)),
    )

    assert response["architecture"] == "deterministic_controller"
    assert response["architecture_label"]
    assert "answer" in response
    assert "citations" in response
    assert "gaps" in response
    assert "architecture_metrics" in response
    assert response["architecture_metrics"]["latency_ms"] >= 0
