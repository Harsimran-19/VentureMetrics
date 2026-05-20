"""Simple evidence sufficiency scoring for the local agent."""

from __future__ import annotations

from dataclasses import dataclass

from venture_metrics_agent.retrieval.retriever import RetrievalResult


CURRENT_TERMS = ("latest", "current", "today", "recent", "2026", "now", "最新", "目前", "今年")


@dataclass(frozen=True)
class EvidenceAssessment:
    is_sufficient: bool
    confidence: str
    reason: str
    needs_web_fallback: bool
    missing_information: list[str]


def assess_evidence(question: str, results: list[RetrievalResult]) -> EvidenceAssessment:
    if not results:
        return EvidenceAssessment(
            is_sufficient=False,
            confidence="Insufficient evidence",
            reason="No relevant internal chunks were retrieved.",
            needs_web_fallback=True,
            missing_information=["No matching indexed source content."],
        )

    unique_sources = {result.source_id for result in results}
    source_types = {result.source_type for result in results if result.source_type}
    reliability = {result.reliability_label for result in results if result.reliability_label}

    score = 0
    if source_types & {"government", "university", "science_park"}:
        score += 2
    if source_types & {"company", "investor"}:
        score += 1
    if len(unique_sources) >= 2:
        score += 1
    if reliability <= {"low"}:
        score -= 1
    if _asks_for_current_data(question):
        score -= 1

    if score >= 3:
        confidence = "High"
        is_sufficient = True
    elif score >= 1:
        confidence = "Medium"
        is_sufficient = True
    else:
        confidence = "Low"
        is_sufficient = False

    missing = []
    if _asks_for_current_data(question):
        missing.append("The question may require current public verification beyond the indexed documents.")
    if len(unique_sources) == 1:
        missing.append("Only one internal source was retrieved.")
    if reliability <= {"low"}:
        missing.append("Retrieved sources are low-reliability or unknown.")

    return EvidenceAssessment(
        is_sufficient=is_sufficient,
        confidence=confidence,
        reason=f"Retrieved {len(results)} chunks from {len(unique_sources)} source(s); score={score}.",
        needs_web_fallback=not is_sufficient,
        missing_information=missing,
    )


def _asks_for_current_data(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in CURRENT_TERMS)
