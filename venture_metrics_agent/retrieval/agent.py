"""Local Venture Metrics research agent."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from venture_metrics_agent.llm.prompts import SYSTEM_PROMPT, answer_prompt
from venture_metrics_agent.llm.provider import LLMProvider
from venture_metrics_agent.observability import record_agent_response
from venture_metrics_agent.retrieval.evidence_scorer import assess_evidence
from venture_metrics_agent.retrieval.retriever import (
    RetrievalResult,
    clean_display_text,
    results_to_context,
    retrieve_internal_evidence,
    unique_citations,
)
from venture_metrics_agent.retrieval.web_search import WebResult, tavily_search, web_results_to_context


@dataclass(frozen=True)
class QueryOptions:
    top_k: int = 8
    use_web_fallback: bool = True


def answer_question(
    db_path: str | Path,
    question: str,
    *,
    options: QueryOptions | None = None,
    llm: LLMProvider | None = None,
    chat_history: list[dict[str, str]] | None = None,
    telemetry_session_id: str | None = None,
) -> dict[str, Any]:
    options = options or QueryOptions()
    llm = llm or LLMProvider()

    results = retrieve_internal_evidence(db_path, question, top_k=options.top_k)
    assessment = assess_evidence(question, results)
    web_results: list[WebResult] = []
    web_error: str | None = None
    should_use_web = options.use_web_fallback and (assessment.needs_web_fallback or _asks_for_current_data(question))
    if should_use_web:
        try:
            web_results = tavily_search(question, max_results=4)
        except RuntimeError as exc:
            web_error = str(exc)

    citations = [*unique_citations(results), *unique_web_citations(web_results)]
    source_mode = _source_mode(results, web_results)

    if not results and not web_results:
        response = {
            "answer": "I do not have enough indexed internal evidence to answer this question yet.",
            "confidence": "Insufficient evidence",
            "source_mode": "insufficient",
            "citations": [],
            "gaps": [*assessment.missing_information, *([f"Web fallback failed: {web_error}"] if web_error else [])],
            "used_web_fallback": bool(should_use_web),
            "retrieved_evidence": [],
            "web_evidence": [],
        }
        _log_query(db_path, question, response, telemetry_session_id=telemetry_session_id)
        return response

    if llm.is_configured:
        try:
            response = _answer_with_llm(
                question,
                results,
                web_results,
                assessment.confidence,
                assessment.missing_information,
                source_mode,
                llm,
                chat_history or [],
            )
            response["citations"] = citations
            response.setdefault("gaps", assessment.missing_information)
        except RuntimeError as exc:
            response = _extractive_answer(
                question,
                results,
                web_results,
                assessment.confidence,
                citations,
                assessment.missing_information,
                source_mode,
            )
            response["gaps"] = [*response.get("gaps", []), _friendly_llm_gap(exc)]
    else:
        response = _extractive_answer(
            question,
            results,
            web_results,
            assessment.confidence,
            citations,
            assessment.missing_information,
            source_mode,
        )

    if web_error:
        response["gaps"] = [*response.get("gaps", []), _friendly_web_gap(web_error)]
    response["source_mode"] = source_mode
    response["used_web_fallback"] = bool(should_use_web)
    response["retrieved_evidence"] = [_evidence_payload(result) for result in results]
    response["web_evidence"] = [_web_payload(result) for result in web_results]
    _log_query(db_path, question, response, telemetry_session_id=telemetry_session_id)
    return response


def _answer_with_llm(
    question: str,
    results: list[RetrievalResult],
    web_results: list[WebResult],
    confidence: str,
    gaps: list[str],
    source_mode: str,
    llm: LLMProvider,
    chat_history: list[dict[str, str]],
) -> dict[str, Any]:
    context_parts = []
    if results:
        context_parts.append("Internal indexed evidence:\n" + results_to_context(results))
    if web_results:
        context_parts.append("Web fallback evidence:\n" + web_results_to_context(web_results))
    context = "\n\n".join(context_parts)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": answer_prompt(
                question,
                context,
                confidence,
                gaps,
                source_mode=source_mode,
                chat_history=chat_history,
            ),
        },
    ]
    response = llm.complete_json(messages)
    response["source_mode"] = source_mode
    return response


def _extractive_answer(
    question: str,
    results: list[RetrievalResult],
    web_results: list[WebResult],
    confidence: str,
    citations: list[dict[str, Any]],
    gaps: list[str],
    source_mode: str,
) -> dict[str, Any]:
    answer = _compose_fallback_answer(results, web_results, citations, gaps)
    return {
        "answer": answer,
        "confidence": confidence,
        "source_mode": source_mode,
        "citations": citations,
        "gaps": gaps,
    }


def _compose_fallback_answer(
    results: list[RetrievalResult],
    web_results: list[WebResult],
    citations: list[dict[str, Any]],
    gaps: list[str],
) -> str:
    if not results and not web_results:
        return "I do not have enough evidence to answer that yet."

    source_lines = []
    for index, citation in enumerate(citations[:4], start=1):
        title = clean_display_text(str(citation.get("title") or "Untitled source"))
        source_type = citation.get("source_type") or "source"
        reliability = citation.get("reliability") or "unrated"
        source_lines.append(f"[{index}] {title} ({source_type}, {reliability})")

    parts = []
    if source_lines:
        parts.append("I found relevant evidence in " + "; ".join(source_lines) + ".")

    notable_points = _notable_points(results, web_results)
    if notable_points:
        parts.append("The clearest supported points are:\n" + "\n".join(notable_points))
    else:
        parts.append("The retrieved sources appear relevant, but the local answer synthesis service is unavailable, so I am keeping the answer conservative instead of over-interpreting the source text.")

    if gaps:
        parts.append("Remaining gap: " + gaps[0])
    return "\n\n".join(parts)


def _short_snippet(text: str, limit: int = 300) -> str:
    cleaned = clean_display_text(text)
    if len(cleaned) <= limit:
        return cleaned
    truncated = cleaned[:limit].rsplit(" ", 1)[0].strip()
    return truncated + "..."


def _notable_points(results: list[RetrievalResult], web_results: list[WebResult]) -> list[str]:
    points: list[str] = []
    for index, result in enumerate(results[:3], start=1):
        sentence = _best_sentence(result.text)
        if not sentence:
            title = clean_display_text(result.title or result.source_domain or f"Source {result.source_id}")
            sentence = f"{title} is a matching {result.source_type or 'internal'} source for this question."
        if sentence:
            points.append(f"- {sentence} [{index}]")
    offset = len(points)
    for web_index, result in enumerate(web_results[:2], start=offset + 1):
        sentence = _best_sentence(result.content)
        if not sentence:
            sentence = f"{clean_display_text(result.title)} is a matching web source for this question."
        if sentence:
            points.append(f"- {sentence} [{web_index}]")
    return points[:4]


def _best_sentence(text: str, limit: int = 240) -> str | None:
    cleaned = clean_display_text(text)
    if not cleaned:
        return None

    candidates = re.split(r"(?<=[.!?。！？])\s+|\s{2,}|\s[+|]\s", cleaned)
    noise_terms = {
        "copyright",
        "privacy policy",
        "disclaimer",
        "contact us",
        "menu",
        "subscribe",
        "javascript",
        ".jpg",
        "prev)",
        "next)",
    }
    for candidate in candidates:
        sentence = candidate.strip(" -|")
        lowered = sentence.lower()
        if len(sentence) < 70:
            continue
        if sentence.count("+") > 4:
            continue
        if any(term in lowered for term in noise_terms):
            continue
        if len(sentence) > limit:
            sentence = sentence[:limit].rsplit(" ", 1)[0].strip() + "..."
        return sentence
    lowered_cleaned = cleaned.lower()
    if cleaned.count("+") > 4 or cleaned.startswith("ENG 繁") or any(term in lowered_cleaned for term in noise_terms):
        return None
    return _short_snippet(cleaned, limit=limit) or None


def _friendly_llm_gap(exc: RuntimeError) -> str:
    text = str(exc).lower()
    if "nodename" in text or "connection" in text or "timed out" in text:
        return "Answer synthesis service was unavailable locally, so this response used retrieved evidence directly."
    return "Answer synthesis service returned an error, so this response used retrieved evidence directly."


def _friendly_web_gap(error: str) -> str:
    lowered = error.lower()
    if "missing" in lowered:
        return "Web search is not configured in this local environment."
    if "connection" in lowered or "nodename" in lowered or "timed out" in lowered:
        return "Web search was unavailable from this local environment."
    return "Web search could not complete for this question."


def _evidence_payload(result: RetrievalResult) -> dict[str, Any]:
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


def unique_web_citations(results: list[WebResult], *, limit: int = 4) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for result in results:
        if result.url in seen:
            continue
        citations.append(result.citation())
        seen.add(result.url)
        if len(citations) >= limit:
            break
    return citations


def _source_mode(internal_results: list[RetrievalResult], web_results: list[WebResult]) -> str:
    if internal_results and web_results:
        return "internal_plus_web"
    if web_results:
        return "web_only"
    if internal_results:
        return "internal_only"
    return "insufficient"


def _asks_for_current_data(question: str) -> bool:
    return bool(re.search(r"\b(latest|current|today|this week|recent|now|2026)\b|最新|目前|本周|今年", question, re.I))


def _log_query(
    db_path: str | Path,
    question: str,
    response: dict[str, Any],
    *,
    telemetry_session_id: str | None = None,
) -> None:
    record_agent_response(
        db_path,
        question,
        response,
        agent_name="retrieval_agent",
        session_external_id=telemetry_session_id,
    )
