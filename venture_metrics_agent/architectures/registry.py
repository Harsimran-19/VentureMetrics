"""Registry for architecture experiment adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from venture_metrics_agent.architectures.adapters import (
    CAGPackAdapter,
    CoverageRAGAdapter,
    DeterministicControllerAdapter,
    LinearRAGAdapter,
    PlanExecuteAdapter,
    ReActLoopAdapter,
    RLMExperimentAdapter,
)
from venture_metrics_agent.architectures.base import ArchitectureAdapter, ArchitectureOptions
from venture_metrics_agent.llm.provider import LLMProvider


_ADAPTERS: dict[str, ArchitectureAdapter] = {
    adapter.metadata.id: adapter
    for adapter in [
        DeterministicControllerAdapter(),
        CoverageRAGAdapter(),
        PlanExecuteAdapter(),
        ReActLoopAdapter(),
        LinearRAGAdapter(),
        CAGPackAdapter(),
        RLMExperimentAdapter(),
    ]
}


def list_architectures() -> list[dict[str, Any]]:
    return [adapter.metadata.as_dict() for adapter in _ADAPTERS.values()]


def get_architecture(architecture_id: str) -> ArchitectureAdapter:
    try:
        return _ADAPTERS[architecture_id]
    except KeyError as exc:
        known = ", ".join(sorted(_ADAPTERS))
        raise ValueError(f"Unknown architecture '{architecture_id}'. Known architectures: {known}") from exc


def run_architecture(
    architecture_id: str,
    db_path: str | Path,
    question: str,
    *,
    options: ArchitectureOptions | None = None,
    llm: LLMProvider | None = None,
    chat_history: list[dict[str, str]] | None = None,
    telemetry_session_id: str | None = None,
) -> dict[str, Any]:
    adapter = get_architecture(architecture_id)
    result = adapter.run(
        db_path,
        question,
        options=options or ArchitectureOptions(),
        llm=llm,
        chat_history=chat_history,
        telemetry_session_id=telemetry_session_id,
    )
    return result.as_dict()


def run_architectures(
    architecture_ids: list[str],
    db_path: str | Path,
    question: str,
    *,
    options: ArchitectureOptions | None = None,
    llm: LLMProvider | None = None,
    chat_history: list[dict[str, str]] | None = None,
    telemetry_session_id: str | None = None,
) -> list[dict[str, Any]]:
    selected = architecture_ids or ["deterministic_controller"]
    return [
        run_architecture(
            architecture_id,
            db_path,
            question,
            options=options,
            llm=llm,
            chat_history=chat_history,
            telemetry_session_id=telemetry_session_id,
        )
        for architecture_id in selected
    ]
