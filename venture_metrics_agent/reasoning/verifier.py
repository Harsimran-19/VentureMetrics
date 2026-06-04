"""Deterministic evidence verification for the reasoning controller."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from venture_metrics_agent.retrieval.evidence_scorer import EvidenceAssessment
from venture_metrics_agent.retrieval.retriever import RetrievalResult, clean_display_text
from venture_metrics_agent.retrieval.web_search import WebResult


STOPWORDS = {
    "what",
    "which",
    "where",
    "when",
    "who",
    "could",
    "would",
    "you",
    "me",
    "more",
    "tell",
    "please",
    "does",
    "do",
    "are",
    "is",
    "the",
    "and",
    "or",
    "for",
    "from",
    "to",
    "in",
    "with",
    "about",
    "have",
    "has",
    "give",
    "show",
    "find",
    "list",
    "search",
    "web",
    "too",
    "answer",
    "mention",
    "mentions",
    "appear",
    "appears",
    "most",
    "relevant",
    "indexed",
    "source",
    "sources",
    "evidence",
    "related",
    "information",
    "data",
    "我们",
    "哪些",
    "什么",
    "有关",
}
REGION_TERMS = {"hong", "kong", "hk", "gba", "shenzhen", "greater", "bay", "香港", "深圳", "大湾区"}
HK_DOMAIN_HINTS = ("edu.hk", ".hk", "hkust", "cuhk", "hku", "polyu", "cityu", "eduhk", "hkbu", "lingnan")
SHENZHEN_DOMAIN_HINTS = ("sz", "shenzhen")


@dataclass(frozen=True)
class VerifiedEvidence:
    accepted_internal: list[RetrievalResult]
    rejected_internal: list[dict[str, Any]]
    accepted_web: list[WebResult]
    confidence: str
    answerable: bool
    needs_more_evidence: bool
    reason: str
    missing_information: list[str] = field(default_factory=list)
    query_terms: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "accepted_internal_count": len(self.accepted_internal),
            "rejected_internal_count": len(self.rejected_internal),
            "accepted_web_count": len(self.accepted_web),
            "confidence": self.confidence,
            "answerable": self.answerable,
            "needs_more_evidence": self.needs_more_evidence,
            "reason": self.reason,
            "missing_information": self.missing_information,
            "query_terms": self.query_terms,
            "accepted_source_ids": sorted({result.source_id for result in self.accepted_internal}),
            "rejected": self.rejected_internal[:5],
        }


def verify_evidence(
    question: str,
    internal_results: list[RetrievalResult],
    assessment: EvidenceAssessment | None,
    web_results: list[WebResult] | None = None,
) -> VerifiedEvidence:
    query_terms = query_terms_for_question(question)
    accepted: list[RetrievalResult] = []
    rejected: list[dict[str, Any]] = []

    for result in internal_results:
        score, reason = _internal_relevance(question, query_terms, result)
        if score >= 2:
            accepted.append(result)
        else:
            rejected.append(
                {
                    "source_id": result.source_id,
                    "title": result.title,
                    "url": result.url,
                    "relevance_score": score,
                    "reason": reason,
                }
            )

    accepted_web = list(web_results or [])
    confidence = _confidence(assessment, accepted, accepted_web)
    missing = _missing_information(question, accepted, rejected, assessment, accepted_web)
    answerable = bool(accepted or accepted_web)
    needs_more = not answerable or confidence in {"Low", "Insufficient evidence"}
    reason = _reason(accepted, rejected, accepted_web, confidence)

    return VerifiedEvidence(
        accepted_internal=accepted,
        rejected_internal=rejected,
        accepted_web=accepted_web,
        confidence=confidence,
        answerable=answerable,
        needs_more_evidence=needs_more,
        reason=reason,
        missing_information=missing,
        query_terms=query_terms,
    )


def _internal_relevance(question: str, query_terms: list[str], result: RetrievalResult) -> tuple[int, str]:
    haystack = _haystack(result)
    required_phrases = _required_entity_phrases(question)
    missing_phrases = [phrase for phrase in required_phrases if not _contains_phrase(haystack, phrase)]
    if missing_phrases:
        return (
            -2,
            "The source text does not mention the required entity phrase(s): "
            + ", ".join(missing_phrases[:4])
            + ".",
        )
    if not query_terms:
        return (1, "No specific query terms were available for relevance checking.")

    hits = [term for term in query_terms if term in haystack]
    score = len(hits)
    if required_phrases:
        score += 2

    question_regions = [term for term in query_terms if term in REGION_TERMS]
    if question_regions and not _matches_requested_region(question_regions, result, haystack):
        score -= 2
        return (score, "The source text does not match the region requested in the question.")

    if score <= 0:
        return (score, "The source text does not cover the main terms in the question.")
    if score == 1 and len(query_terms) >= 3:
        return (score, "The source text only weakly overlaps with the question.")
    return (score, f"Matched query terms: {', '.join(hits[:6])}.")


def _confidence(
    assessment: EvidenceAssessment | None,
    accepted_internal: list[RetrievalResult],
    accepted_web: list[WebResult],
) -> str:
    if not accepted_internal and not accepted_web:
        return "Insufficient evidence"

    base = assessment.confidence if assessment else "Low"
    unique_sources = {result.source_id for result in accepted_internal}
    credible = {
        result.source_type
        for result in accepted_internal
        if result.source_type in {"government", "university", "science_park", "company", "investor", "report", "database"}
    }

    if accepted_web and not accepted_internal:
        return "Medium" if len(accepted_web) >= 2 else "Low"
    if accepted_web and base in {"Insufficient evidence", "Low"}:
        return "Medium"
    if base == "High" and len(unique_sources) >= 2 and credible:
        return "High"
    if base in {"High", "Medium"} and accepted_internal:
        return "Medium"
    return "Low"


def _missing_information(
    question: str,
    accepted: list[RetrievalResult],
    rejected: list[dict[str, Any]],
    assessment: EvidenceAssessment | None,
    accepted_web: list[WebResult],
) -> list[str]:
    missing = list(assessment.missing_information if assessment else [])
    if not accepted and not accepted_web:
        missing.append("Retrieved internal chunks did not pass relevance verification.")
    if rejected:
        missing.append(f"{len(rejected)} retrieved internal chunk(s) were rejected as weak or off-topic.")
    if _asks_for_region(question) and not accepted_web and not any(_has_requested_region(question, result) for result in accepted):
        missing.append("No accepted source clearly matches the requested region.")
    return _dedupe(missing)


def _reason(
    accepted_internal: list[RetrievalResult],
    rejected_internal: list[dict[str, Any]],
    accepted_web: list[WebResult],
    confidence: str,
) -> str:
    return (
        f"Accepted {len(accepted_internal)} internal chunk(s), "
        f"rejected {len(rejected_internal)} internal chunk(s), "
        f"accepted {len(accepted_web)} web result(s); confidence={confidence}."
    )


def query_terms_for_question(question: str) -> list[str]:
    raw_terms = re.findall(r"[\w\u4e00-\u9fff]{2,}", question.lower())
    terms: list[str] = []
    for term in raw_terms:
        normalized = _normalize_term(term)
        if not normalized or normalized in STOPWORDS:
            continue
        if normalized not in terms:
            terms.append(normalized)
    return terms[:12]


def _required_entity_phrases(question: str) -> list[str]:
    phrases: list[str] = []
    for match in re.findall(r"\b[\w\u4e00-\u9fff]+(?:[-'][\w\u4e00-\u9fff]+)+\b", question):
        # Treat hyphenated proper nouns such as "T-Hub" as required entities,
        # but do not require generic descriptors like "early-stage" verbatim.
        if not _looks_like_named_entity(match):
            continue
        normalized = _normalize_phrase(match).lower()
        if normalized and normalized not in phrases:
            phrases.append(normalized)
    return phrases[:4]


def _looks_like_named_entity(text: str) -> bool:
    compact = re.sub(r"[-'_]+", "", text)
    if any(char.isdigit() for char in compact):
        return True
    letters = [char for char in compact if char.isalpha()]
    if not letters:
        return False
    return any(char.isupper() for char in letters)


def _normalize_term(term: str) -> str:
    if term.endswith("ies") and len(term) > 4:
        return term[:-3] + "y"
    if term.endswith("s") and len(term) > 4:
        return term[:-1]
    return term


def _haystack(result: RetrievalResult) -> str:
    return _normalize_phrase(
        clean_display_text(
        f"{result.title or ''} {result.source_domain or ''} {result.source_type or ''} {result.text}"
        ).lower()
    )


def _normalize_phrase(text: str) -> str:
    return re.sub(r"[-'_]+", " ", text).strip()


def _contains_phrase(haystack: str, phrase: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", haystack))


def _asks_for_region(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in REGION_TERMS)


def _has_requested_region(question: str, result: RetrievalResult) -> bool:
    haystack = _haystack(result)
    question_regions = [term for term in query_terms_for_question(question) if term in REGION_TERMS]
    return _matches_requested_region(question_regions, result, haystack)


def _matches_requested_region(question_regions: list[str], result: RetrievalResult, haystack: str) -> bool:
    if any(term in haystack for term in question_regions):
        return True

    domain = (result.source_domain or result.url or "").lower()
    asks_hk = any(term in {"hong", "kong", "hk", "香港"} for term in question_regions)
    asks_shenzhen = any(term in {"shenzhen", "深圳"} for term in question_regions)
    asks_gba = any(term in {"gba", "greater", "bay", "大湾区"} for term in question_regions)

    if asks_hk and any(hint in domain for hint in HK_DOMAIN_HINTS):
        return True
    if asks_shenzhen and any(hint in domain for hint in SHENZHEN_DOMAIN_HINTS):
        return True
    if asks_gba and (any(hint in domain for hint in HK_DOMAIN_HINTS) or any(hint in domain for hint in SHENZHEN_DOMAIN_HINTS)):
        return True
    return False


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        if item in seen:
            continue
        deduped.append(item)
        seen.add(item)
    return deduped
