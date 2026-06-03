"""Shared contract for architecture experiments."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from venture_metrics_agent.llm.provider import LLMProvider


@dataclass(frozen=True)
class ArchitectureOptions:
    top_k: int = 8
    use_web_fallback: bool = True
    max_web_results: int = 4
    remember_web_results: bool = False
    max_iterations: int = 3


@dataclass(frozen=True)
class ArchitectureMetadata:
    id: str
    label: str
    family: str
    status: str
    description: str
    strengths: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "family": self.family,
            "status": self.status,
            "description": self.description,
            "strengths": self.strengths,
            "limitations": self.limitations,
        }


@dataclass(frozen=True)
class ArchitectureResult:
    architecture: str
    label: str
    response: dict[str, Any]
    metrics: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        payload = dict(self.response)
        payload["architecture"] = self.architecture
        payload["architecture_label"] = self.label
        payload["architecture_metrics"] = self.metrics
        return payload


class ArchitectureAdapter(Protocol):
    metadata: ArchitectureMetadata

    def run(
        self,
        db_path: str | Path,
        question: str,
        *,
        options: ArchitectureOptions,
        llm: LLMProvider | None = None,
        chat_history: list[dict[str, str]] | None = None,
        telemetry_session_id: str | None = None,
    ) -> ArchitectureResult:
        ...


def timed_response(
    architecture: str,
    label: str,
    started_at: float,
    response: dict[str, Any],
    *,
    tool_calls: int | None = None,
    extra_metrics: dict[str, Any] | None = None,
) -> ArchitectureResult:
    metrics = {
        "latency_ms": int((time.perf_counter() - started_at) * 1000),
        "tool_calls": tool_calls if tool_calls is not None else _tool_count(response),
        "citation_count": len(response.get("citations") or []),
        "used_web": bool(response.get("used_web_fallback")),
        "source_mode": response.get("source_mode"),
        "confidence": response.get("confidence"),
    }
    if extra_metrics:
        metrics.update(extra_metrics)
    return ArchitectureResult(architecture=architecture, label=label, response=response, metrics=metrics)


def normalize_response(response: dict[str, Any]) -> dict[str, Any]:
    response = dict(response)
    response.setdefault("answer", "")
    response.setdefault("confidence", "Insufficient evidence")
    response.setdefault("source_mode", "insufficient")
    response.setdefault("citations", [])
    response.setdefault("gaps", [])
    response.setdefault("used_web_fallback", False)
    response.setdefault("retrieved_evidence", [])
    response.setdefault("web_evidence", [])
    response.setdefault("reasoning_trace", [])
    return response


def _tool_count(response: dict[str, Any]) -> int:
    trace = response.get("reasoning_trace") or []
    return sum(1 for step in trace if isinstance(step, dict) and step.get("tool"))
