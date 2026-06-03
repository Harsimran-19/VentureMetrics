"""Helpers shared by architecture experiment adapters."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from venture_metrics_agent.retrieval.agent import unique_web_citations
from venture_metrics_agent.retrieval.evidence_scorer import EvidenceAssessment
from venture_metrics_agent.retrieval.retriever import (
    RetrievalResult,
    clean_display_text,
    unique_citations,
)
from venture_metrics_agent.retrieval.web_search import WebResult
from venture_metrics_agent.llm.provider import LLMProvider
from venture_metrics_agent.reasoning.casual import casual_response
from venture_metrics_agent.reasoning.router import route_message
from venture_metrics_agent.reasoning.verifier import VerifiedEvidence, query_terms_for_question
from venture_metrics_agent.reasoning.web_memory import remember_web_results


COMPARISON_TERMS = ("compare", "versus", " vs ", "between", "difference", "differences", "对比", "比较")
CURRENT_TERMS = ("latest", "current", "today", "recent", "now", "2026", "最新", "目前", "今年")
DIMENSION_TERMS = {
    "policy": ("policy", "policies", "government", "政策"),
    "funding": ("funding", "grant", "grants", "fund", "subsidy", "programme", "program", "资助", "資助"),
    "ecosystem": ("ecosystem", "incubator", "science park", "accelerator", "university", "mentor", "生态", "孵化器", "科技园"),
    "hong_kong": ("hong kong", "hk", "香港"),
    "shenzhen": ("shenzhen", "深圳"),
}


def merge_internal_results(groups: list[list[RetrievalResult]], *, limit: int | None = None) -> list[RetrievalResult]:
    seen: set[int] = set()
    merged: list[RetrievalResult] = []
    for group in groups:
        for result in group:
            if result.chunk_id in seen:
                continue
            merged.append(result)
            seen.add(result.chunk_id)
            if limit and len(merged) >= limit:
                return merged
    return merged


def answer_dimensions(question: str) -> list[str]:
    lowered = question.lower()
    dimensions = [name for name, terms in DIMENSION_TERMS.items() if any(term in lowered for term in terms)]
    if any(term in lowered for term in COMPARISON_TERMS):
        dimensions.append("comparison")
    if any(term in lowered for term in CURRENT_TERMS):
        dimensions.append("current")
    return _dedupe(dimensions)


def missing_dimensions(question: str, results: list[RetrievalResult], web_results: list[WebResult] | None = None) -> list[str]:
    dimensions = answer_dimensions(question)
    if not dimensions:
        return []
    haystack = " ".join(
        clean_display_text(f"{result.title or ''} {result.source_domain or ''} {result.text}") for result in results
    ).lower()
    if web_results:
        haystack += " " + " ".join(clean_display_text(f"{result.title} {result.content}") for result in web_results).lower()
    missing: list[str] = []
    for dimension in dimensions:
        if dimension in {"comparison", "current"}:
            continue
        if not any(term in haystack for term in DIMENSION_TERMS[dimension]):
            missing.append(dimension)
    if "comparison" in dimensions and ("hong_kong" in dimensions and "shenzhen" in dimensions):
        if "hong_kong" in missing or "shenzhen" in missing:
            missing.append("comparison_coverage")
    return _dedupe(missing)


def should_use_web_for_coverage(
    question: str,
    assessment: EvidenceAssessment | None,
    verified: VerifiedEvidence,
    *,
    web_allowed: bool,
) -> tuple[bool, list[str]]:
    missing = missing_dimensions(question, verified.accepted_internal)
    lowered = question.lower()
    asks_current = any(term in lowered for term in CURRENT_TERMS)
    broad_research = any(term in lowered for term in COMPARISON_TERMS) or len(answer_dimensions(question)) >= 2
    weak_confidence = verified.confidence in {"Low", "Insufficient evidence"}
    insufficient = bool(assessment and assessment.needs_web_fallback) or verified.needs_more_evidence
    should = web_allowed and (asks_current or broad_research and missing or weak_confidence or insufficient)
    return should, missing


def synthesize_extractive(
    question: str,
    internal_results: list[RetrievalResult],
    web_results: list[WebResult],
    *,
    confidence: str,
    source_mode: str,
    gaps: list[str],
    trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    citations = [*unique_citations(internal_results), *unique_web_citations(web_results)]
    points = _points(internal_results, web_results)
    if points:
        answer = "\n".join(points)
    else:
        answer = "I do not have enough reliable evidence to answer this question yet."
    return {
        "answer": answer,
        "confidence": confidence,
        "source_mode": source_mode,
        "citations": citations,
        "gaps": _dedupe(gaps),
        "used_web_fallback": bool(web_results),
        "retrieved_evidence": [_internal_payload(result) for result in internal_results],
        "web_evidence": [_web_payload(result) for result in web_results],
        "reasoning_trace": trace or [],
    }


def maybe_remember_web(
    db_path: str | Path,
    question: str,
    web_results: list[WebResult],
    *,
    enabled: bool,
    trace: list[dict[str, Any]],
) -> None:
    if not enabled or not web_results:
        return
    stats = remember_web_results(db_path, question=question, results=web_results)
    trace.append(
        {
            "phase": "act",
            "decision": "remember_web_evidence",
            "tool": "source_registry",
            "observation": stats,
        }
    )


def query_variants(question: str, *, max_queries: int = 4) -> list[str]:
    terms = query_terms_for_question(question)
    variants = [question]
    regions = [term for term in terms if term in {"hong", "kong", "hk", "shenzhen", "香港", "深圳"}]
    topics = [term for term in terms if term not in regions]
    if regions and topics:
        for region in regions[:2]:
            variants.append(" ".join([region, *topics[:6]]))
    compact = " ".join(terms[:8])
    if compact:
        variants.append(compact)
    return _dedupe(variants)[:max_queries]


def source_mode(internal_results: list[RetrievalResult], web_results: list[WebResult]) -> str:
    if internal_results and web_results:
        return "internal_plus_web"
    if web_results:
        return "web_only"
    if internal_results:
        return "internal_only"
    return "insufficient"


def confidence_from_evidence(
    assessment: EvidenceAssessment | None,
    verified: VerifiedEvidence,
    web_results: list[WebResult],
) -> str:
    if not verified.accepted_internal and not web_results:
        return "Insufficient evidence"
    if web_results and verified.confidence in {"Low", "Insufficient evidence"}:
        return "Medium"
    return verified.confidence if assessment else ("Medium" if web_results else "Low")


def direct_route_response(
    question: str,
    *,
    llm: LLMProvider | None,
    chat_history: list[dict[str, str]] | None,
    use_web_fallback: bool,
) -> dict[str, Any] | None:
    route = route_message(question, use_web_fallback=use_web_fallback)
    if route.needs_research:
        return None
    if route.needs_clarification:
        answer = "Can you narrow the question a bit? I need a specific topic, source type, company, programme, or region to research."
        confidence = "Insufficient evidence"
        source = "insufficient"
        gaps = ["No research tools were used because the request was underspecified."]
    else:
        answer = casual_response(question, intent=route.intent, chat_history=chat_history or [], llm=llm or _NoLLM())
        confidence = "High"
        source = "no_tools"
        gaps = []
    return {
        "answer": answer,
        "confidence": confidence,
        "source_mode": source,
        "citations": [],
        "gaps": gaps,
        "used_web_fallback": False,
        "retrieved_evidence": [],
        "web_evidence": [],
        "route": route.as_dict(),
        "reasoning_trace": [
            {
                "phase": "route",
                "decision": route.intent,
                "reason": route.reason,
                "observation": route.as_dict(),
            }
        ],
    }


def route_payload(question: str, *, use_web_fallback: bool) -> dict[str, Any]:
    return route_message(question, use_web_fallback=use_web_fallback).as_dict()


class _NoLLM:
    is_configured = False


def _points(internal_results: list[RetrievalResult], web_results: list[WebResult]) -> list[str]:
    points: list[str] = []
    for index, result in enumerate(internal_results[:4], start=1):
        snippet = _best_sentence(result.text)
        title = clean_display_text(result.title or result.source_domain or f"Source {result.source_id}")
        points.append(f"- {snippet or title} [{index}]")
    offset = len(points)
    for index, result in enumerate(web_results[:3], start=offset + 1):
        snippet = _best_sentence(result.content)
        title = clean_display_text(result.title or result.url)
        points.append(f"- {snippet or title} [{index}]")
    return points


def _best_sentence(text: str, limit: int = 280) -> str | None:
    cleaned = clean_display_text(text)
    if not cleaned:
        return None
    for candidate in re.split(r"(?<=[.!?。！？])\s+|\s{2,}", cleaned):
        candidate = candidate.strip(" -|")
        if len(candidate) < 60:
            continue
        lowered = candidate.lower()
        if any(term in lowered for term in {"copyright", "privacy", "menu", "subscribe", "javascript"}):
            continue
        if len(candidate) > limit:
            return candidate[:limit].rsplit(" ", 1)[0].strip() + "..."
        return candidate
    return cleaned[:limit].rsplit(" ", 1)[0].strip() + "..." if len(cleaned) > limit else cleaned


def _internal_payload(result: RetrievalResult) -> dict[str, Any]:
    return {
        "chunk_id": result.chunk_id,
        "source_id": result.source_id,
        "title": result.title,
        "url": result.url,
        "source_type": result.source_type,
        "reliability": result.reliability_label,
        "score": result.score,
        "snippet": clean_display_text(result.text)[:700],
    }


def _web_payload(result: WebResult) -> dict[str, Any]:
    return {
        "title": result.title,
        "url": result.url,
        "source_type": "web",
        "reliability": "needs_review",
        "score": result.score,
        "snippet": clean_display_text(result.content)[:700],
    }


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        if item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped
