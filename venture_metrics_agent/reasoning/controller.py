"""Experimental reasoning-style controller for Venture Metrics."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from venture_metrics_agent.llm.prompts import SYSTEM_PROMPT, answer_prompt
from venture_metrics_agent.llm.provider import LLMProvider
from venture_metrics_agent.ingestion.source_registry import init_db
from venture_metrics_agent.retrieval.agent import unique_web_citations
from venture_metrics_agent.retrieval.evidence_scorer import EvidenceAssessment
from venture_metrics_agent.retrieval.retriever import (
    RetrievalResult,
    clean_display_text,
    results_to_context,
    unique_citations,
)
from venture_metrics_agent.retrieval.web_search import WebResult, web_results_to_context
from venture_metrics_agent.reasoning.planner import internal_search_queries, should_refine_internal_search
from venture_metrics_agent.reasoning.router import RouteDecision, route_message
from venture_metrics_agent.reasoning.casual import casual_response
from venture_metrics_agent.reasoning.tools import InternalSearchObservation, ReasoningToolbox, WebSearchObservation
from venture_metrics_agent.reasoning.verifier import VerifiedEvidence, verify_evidence
from venture_metrics_agent.reasoning.web_memory import remember_web_results
from venture_metrics_agent.reasoning.workspace import ResearchWorkspace


@dataclass(frozen=True)
class ReasoningOptions:
    top_k: int = 8
    use_web_fallback: bool = True
    max_web_results: int = 4
    max_internal_iterations: int = 2
    remember_web_results: bool = True


def answer_question_reasoning(
    db_path: str | Path,
    question: str,
    *,
    options: ReasoningOptions | None = None,
    llm: LLMProvider | None = None,
    chat_history: list[dict[str, str]] | None = None,
    toolbox: ReasoningToolbox | None = None,
) -> dict[str, Any]:
    options = options or ReasoningOptions()
    llm = llm or LLMProvider()

    route = route_message(question, use_web_fallback=options.use_web_fallback)
    workspace = ResearchWorkspace(question=question, route=route.as_dict())
    workspace.add_step(
        phase="route",
        decision=route.intent,
        reason=route.reason,
        observation=route.as_dict(),
    )

    if not route.needs_research:
        response = _direct_response(question, route, workspace, llm=llm, chat_history=chat_history or [])
        _log_query(db_path, question, response)
        return response

    toolbox = toolbox or ReasoningToolbox(db_path)
    plan = _build_plan(route, question)
    workspace.add_step(
        phase="plan",
        decision="create_research_plan",
        reason="A research task needs controlled tool use before answering.",
        observation={"plan": plan},
    )

    internal_observation: InternalSearchObservation | None = None
    internal_verification: VerifiedEvidence | None = None
    if route.allow_internal_search:
        internal_observation, internal_verification = _run_internal_iterations(
            question,
            toolbox,
            workspace,
            top_k=options.top_k,
            max_iterations=options.max_internal_iterations,
        )

    web_observation: WebSearchObservation | None = None
    if _should_use_web(route, internal_observation, internal_verification):
        workspace.add_step(
            phase="act",
            decision="use_web_search",
            reason=_web_reason(route, internal_observation, internal_verification),
            tool="web_search",
            observation={"query": question, "max_results": options.max_web_results},
        )
        web_observation = toolbox.web_search(question, max_results=options.max_web_results)
        workspace.add_step(
            phase="observe",
            decision="inspect_web_evidence",
            reason="Web search returned public evidence or a recoverable tool error.",
            tool="web_search",
            observation=web_observation.summary(),
        )
        if options.remember_web_results and web_observation.results:
            memory_stats = remember_web_results(db_path, question=question, results=web_observation.results)
            workspace.add_step(
                phase="act",
                decision="remember_web_evidence",
                reason="Useful controlled web-search results were stored for future reuse.",
                tool="source_registry",
                observation=memory_stats,
            )
    else:
        workspace.add_step(
            phase="act",
            decision="skip_web_search",
            reason="The controller did not find a justified reason to use web search.",
            tool="web_search",
        )

    results = internal_observation.results if internal_observation else []
    web_results = web_observation.results if web_observation else []
    assessment = internal_observation.assessment if internal_observation else None
    web_error = web_observation.error if web_observation else None
    response = _synthesize_response(
        question,
        results,
        web_results,
        assessment,
        route,
        workspace,
        llm,
        chat_history or [],
        web_error,
    )
    _log_query(db_path, question, response)
    return response


def _build_plan(route: RouteDecision, question: str) -> list[str]:
    plan = ["Classify whether the message requires tools before doing any retrieval."]
    if route.allow_internal_search:
        plan.append("Search indexed Venture Metrics sources, verify relevance, and refine once if evidence is weak.")
    if route.intent in {"current_research", "external_research"}:
        plan.append("Use public web search only after checking whether local evidence exists.")
    else:
        plan.append("Avoid public web search unless local evidence is missing or weak.")
    plan.append("Validate answerability, confidence, citations, and gaps before responding.")
    return plan


def _run_internal_iterations(
    question: str,
    toolbox: ReasoningToolbox,
    workspace: ResearchWorkspace,
    *,
    top_k: int,
    max_iterations: int,
) -> tuple[InternalSearchObservation, VerifiedEvidence]:
    queries = internal_search_queries(question, max_queries=max_iterations)
    merged_results: list[RetrievalResult] = []
    latest_assessment: EvidenceAssessment | None = None
    latest_verification: VerifiedEvidence | None = None

    for iteration, query in enumerate(queries, start=1):
        decision = "use_internal_corpus" if iteration == 1 else "refine_internal_query"
        reason = (
            "The controller is testing whether local evidence can answer the question."
            if iteration == 1
            else "The previous internal evidence was weak, so the controller is trying a refined local query."
        )
        workspace.add_step(
            phase="act",
            decision=decision,
            reason=reason,
            tool="internal_search",
            observation={"query": query, "top_k": top_k, "iteration": iteration},
        )

        observation = toolbox.internal_search(query, top_k=top_k)
        merged_results = _merge_results(merged_results, observation.results)
        latest_assessment = observation.assessment
        merged_observation = InternalSearchObservation(results=merged_results, assessment=latest_assessment)
        workspace.add_step(
            phase="observe",
            decision="inspect_internal_evidence",
            reason="Internal search returned evidence and an initial sufficiency assessment.",
            tool="internal_search",
            observation={
                **observation.summary(),
                "iteration": iteration,
                "merged_result_count": len(merged_results),
            },
        )

        latest_verification = verify_evidence(question, merged_results, latest_assessment)
        workspace.add_step(
            phase="verify",
            decision="verify_internal_relevance",
            reason="The controller checks whether retrieved chunks actually match the question before using them.",
            observation={**latest_verification.summary(), "iteration": iteration},
        )

        if not should_refine_internal_search(
            latest_verification,
            iteration=iteration,
            max_iterations=len(queries),
        ):
            return merged_observation, latest_verification

    fallback_assessment = latest_assessment or EvidenceAssessment(
        is_sufficient=False,
        confidence="Insufficient evidence",
        reason="No internal search iterations ran.",
        needs_web_fallback=True,
        missing_information=["No internal search iterations ran."],
    )
    fallback_observation = InternalSearchObservation(results=merged_results, assessment=fallback_assessment)
    fallback_verification = latest_verification or verify_evidence(question, merged_results, fallback_assessment)
    return fallback_observation, fallback_verification


def _should_use_web(
    route: RouteDecision,
    internal_observation: InternalSearchObservation | None,
    verification: VerifiedEvidence | None,
) -> bool:
    if not route.allow_web_search or not route.needs_research:
        return False
    if route.intent in {"current_research", "external_research"}:
        return True
    if internal_observation is None or verification is None:
        return False
    return internal_observation.assessment.needs_web_fallback or verification.needs_more_evidence


def _web_reason(
    route: RouteDecision,
    internal_observation: InternalSearchObservation | None,
    verification: VerifiedEvidence | None,
) -> str:
    if route.intent == "current_research":
        return "The question asks for current or recent information."
    if route.intent == "external_research":
        return "The user explicitly asked for external/public web verification."
    if verification and verification.needs_more_evidence:
        return verification.reason
    if internal_observation and internal_observation.assessment.needs_web_fallback:
        return internal_observation.assessment.reason
    return "The controller allowed web search for this research task."


def _direct_response(
    question: str,
    route: RouteDecision,
    workspace: ResearchWorkspace,
    *,
    llm: LLMProvider,
    chat_history: list[dict[str, str]],
) -> dict[str, Any]:
    if route.needs_clarification:
        answer = "Can you narrow the question a bit? I need a specific topic, source type, company, programme, or region to research."
        confidence = "Insufficient evidence"
        source_mode = "insufficient"
        gaps = ["No research tools were used because the request was underspecified."]
    else:
        answer = casual_response(question, intent=route.intent, chat_history=chat_history, llm=llm)
        confidence = "High"
        source_mode = "no_tools"
        gaps = []

    return {
        "answer": answer,
        "confidence": confidence,
        "source_mode": source_mode,
        "citations": [],
        "gaps": gaps,
        "used_web_fallback": False,
        "retrieved_evidence": [],
        "web_evidence": [],
        "route": route.as_dict(),
        "reasoning_trace": workspace.trace(),
    }


def _synthesize_response(
    question: str,
    results: list[RetrievalResult],
    web_results: list[WebResult],
    assessment: EvidenceAssessment | None,
    route: RouteDecision,
    workspace: ResearchWorkspace,
    llm: LLMProvider,
    chat_history: list[dict[str, str]],
    web_error: str | None,
) -> dict[str, Any]:
    verified = verify_evidence(question, results, assessment, web_results)
    accepted_results = verified.accepted_internal
    accepted_web_results = verified.accepted_web
    source_mode = _source_mode(accepted_results, accepted_web_results)
    citations = [*unique_citations(accepted_results), *unique_web_citations(accepted_web_results)]
    confidence = _combined_confidence(route, assessment, accepted_web_results, verified)
    gaps = list(verified.missing_information)
    if web_error:
        gaps.append(_friendly_web_gap(web_error))
    if not citations:
        gaps.append("No reliable source evidence was found.")

    workspace.add_step(
        phase="verify",
        decision="assess_answerability",
        reason="The controller checks whether selected evidence can support a final answer.",
        observation={
            "source_mode": source_mode,
            "confidence": confidence,
            "citation_count": len(citations),
            "gaps": gaps,
            "verification": verified.summary(),
        },
    )

    if not accepted_results and not accepted_web_results:
        response = {
            "answer": "I do not have enough evidence to answer this question yet.",
            "confidence": "Insufficient evidence",
            "source_mode": "insufficient",
            "citations": [],
            "gaps": gaps,
        }
    elif llm.is_configured:
        response = _answer_with_llm(
            question,
            accepted_results,
            accepted_web_results,
            confidence,
            gaps,
            source_mode,
            llm,
            chat_history,
        )
        response["citations"] = citations
        response.setdefault("gaps", gaps)
    else:
        response = _extractive_answer(accepted_results, accepted_web_results, confidence, source_mode, citations, gaps)

    response["source_mode"] = source_mode if citations else "insufficient"
    response["used_web_fallback"] = bool(web_results or web_error)
    response["retrieved_evidence"] = [_evidence_payload(result) for result in accepted_results]
    response["web_evidence"] = [_web_payload(result) for result in accepted_web_results]
    response["rejected_evidence"] = verified.rejected_internal
    response["route"] = route.as_dict()
    response["reasoning_trace"] = workspace.trace()
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
        context_parts.append("Indexed Venture Metrics evidence:\n" + results_to_context(results))
    if web_results:
        context_parts.append("Controlled web evidence:\n" + web_results_to_context(web_results))
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": answer_prompt(
                question,
                "\n\n".join(context_parts),
                confidence,
                gaps,
                source_mode=source_mode,
                chat_history=chat_history,
            ),
        },
    ]
    try:
        return llm.complete_json(messages)
    except RuntimeError as exc:
        response = _extractive_answer(results, web_results, confidence, source_mode, [], gaps)
        response["gaps"] = [*response.get("gaps", []), _friendly_llm_gap(exc)]
        return response


def _extractive_answer(
    results: list[RetrievalResult],
    web_results: list[WebResult],
    confidence: str,
    source_mode: str,
    citations: list[dict[str, Any]],
    gaps: list[str],
) -> dict[str, Any]:
    points: list[str] = []
    for index, result in enumerate(results[:4], start=1):
        snippet = _best_snippet(result.text)
        title = clean_display_text(result.title or result.source_domain or f"Source {result.source_id}")
        points.append(f"- {snippet or title} [{index}]")
    offset = len(points)
    for index, result in enumerate(web_results[:2], start=offset + 1):
        snippet = _best_snippet(result.content)
        points.append(f"- {snippet or clean_display_text(result.title)} [{index}]")

    if points:
        answer = "The controlled research loop found these supported points:\n" + "\n".join(points)
    else:
        answer = "The controller found potentially relevant sources, but not enough clean text to make a stronger claim."

    return {
        "answer": answer,
        "confidence": confidence,
        "source_mode": source_mode,
        "citations": citations,
        "gaps": gaps,
    }


def _combined_confidence(
    route: RouteDecision,
    assessment: EvidenceAssessment | None,
    web_results: list[WebResult],
    verification: VerifiedEvidence,
) -> str:
    if not verification.answerable:
        return "Insufficient evidence"
    if assessment is None:
        return "Low" if web_results else "Insufficient evidence"
    if route.intent == "current_research" and not web_results:
        return "Low"
    if assessment.confidence == "Low" and web_results:
        return "Medium"
    return verification.confidence


def _source_mode(internal_results: list[RetrievalResult], web_results: list[WebResult]) -> str:
    if internal_results and web_results:
        return "internal_plus_web"
    if web_results:
        return "web_only"
    if internal_results:
        return "internal_only"
    return "insufficient"


def _merge_results(existing: list[RetrievalResult], new_results: list[RetrievalResult]) -> list[RetrievalResult]:
    seen = {result.chunk_id for result in existing}
    merged = list(existing)
    for result in new_results:
        if result.chunk_id in seen:
            continue
        merged.append(result)
        seen.add(result.chunk_id)
    return merged


def _best_snippet(text: str, *, limit: int = 260) -> str | None:
    cleaned = clean_display_text(text)
    if not cleaned:
        return None
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rsplit(" ", 1)[0].strip() + "..."


def _friendly_llm_gap(exc: RuntimeError) -> str:
    lowered = str(exc).lower()
    if "connection" in lowered or "timed out" in lowered or "nodename" in lowered:
        return "Answer synthesis service was unavailable, so this response used extracted evidence directly."
    return "Answer synthesis service returned an error, so this response used extracted evidence directly."


def _friendly_web_gap(error: str) -> str:
    lowered = error.lower()
    if "missing" in lowered:
        return "Web search is not configured in this local environment."
    if "connection" in lowered or "timed out" in lowered or "nodename" in lowered:
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


def _log_query(db_path: str | Path, question: str, response: dict[str, Any]) -> None:
    conn = init_db(db_path)
    try:
        conn.execute(
            """
            INSERT INTO query_logs (
                question,
                answer,
                confidence,
                source_mode,
                used_web_fallback,
                citations_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                question,
                response.get("answer", ""),
                response.get("confidence", "Insufficient evidence"),
                response.get("source_mode", "insufficient"),
                1 if response.get("used_web_fallback") else 0,
                json.dumps(response.get("citations", []), ensure_ascii=False),
            ),
        )
        conn.commit()
    finally:
        conn.close()
