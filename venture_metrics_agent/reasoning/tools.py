"""Tool boundary for the reasoning controller."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from venture_metrics_agent.retrieval.evidence_scorer import EvidenceAssessment, assess_evidence
from venture_metrics_agent.retrieval.retriever import RetrievalResult, retrieve_internal_evidence
from venture_metrics_agent.retrieval.web_search import WebResult, tavily_search


@dataclass(frozen=True)
class InternalSearchObservation:
    results: list[RetrievalResult]
    assessment: EvidenceAssessment

    def summary(self) -> dict[str, Any]:
        return {
            "result_count": len(self.results),
            "confidence": self.assessment.confidence,
            "is_sufficient": self.assessment.is_sufficient,
            "needs_more_evidence": self.assessment.needs_web_fallback,
            "reason": self.assessment.reason,
            "missing_information": self.assessment.missing_information,
            "source_ids": sorted({result.source_id for result in self.results}),
        }


@dataclass(frozen=True)
class WebSearchObservation:
    results: list[WebResult]
    error: str | None = None

    def summary(self) -> dict[str, Any]:
        return {
            "result_count": len(self.results),
            "error": self.error,
            "urls": [result.url for result in self.results[:5]],
        }


class ReasoningToolbox:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = db_path

    def internal_search(self, question: str, *, top_k: int = 8) -> InternalSearchObservation:
        results = retrieve_internal_evidence(self.db_path, question, top_k=top_k)
        return InternalSearchObservation(results=results, assessment=assess_evidence(question, results))

    def web_search(self, query: str, *, max_results: int = 4) -> WebSearchObservation:
        try:
            return WebSearchObservation(results=tavily_search(query, max_results=max_results))
        except RuntimeError as exc:
            return WebSearchObservation(results=[], error=str(exc))
