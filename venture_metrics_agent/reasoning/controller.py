"""Experimental reasoning-style controller for Venture Metrics."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from venture_metrics_agent.llm.prompts import (
    CONTEXTUALIZE_SYSTEM_PROMPT,
    ROUTER_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    answer_prompt,
    contextualize_prompt,
    routing_prompt,
)
from venture_metrics_agent.llm.provider import LLMProvider
from venture_metrics_agent.observability import load_chat_history, record_agent_response
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
    telemetry_session_id: str | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    options = options or ReasoningOptions()
    llm = llm or LLMProvider()
    _emit_progress(progress_callback, "thinking", "Thinking...")

    combined_history = _combined_chat_history(
        db_path,
        telemetry_session_id=telemetry_session_id,
        supplied_history=chat_history or [],
        current_question=question,
    )
    route, route_source = _route_with_reasoner(
        question,
        use_web_fallback=options.use_web_fallback,
        llm=llm,
        chat_history=combined_history,
    )
    workspace = ResearchWorkspace(question=question, route=route.as_dict())
    workspace.add_step(
        phase="route",
        decision=route.intent,
        reason=route.reason,
        observation={**route.as_dict(), "route_source": route_source},
    )
    _emit_progress(progress_callback, "route", _route_status_message(route), route=route.as_dict())

    if not route.needs_research:
        _emit_progress(progress_callback, "writing", _direct_status_message(route))
        response = _direct_response(question, route, workspace, llm=llm, chat_history=combined_history)
        _log_query(db_path, question, response, telemetry_session_id=telemetry_session_id)
        return response

    research_question = _standalone_research_question(question, combined_history, llm, workspace)
    toolbox = toolbox or ReasoningToolbox(db_path)
    plan = _build_plan(route, research_question)
    workspace.add_step(
        phase="plan",
        decision="create_research_plan",
        reason="A research task needs controlled tool use before answering.",
        observation={"plan": plan},
    )

    internal_observation: InternalSearchObservation | None = None
    internal_verification: VerifiedEvidence | None = None
    if route.allow_internal_search:
        _emit_progress(progress_callback, "internal_search", "Searching saved sources...")
        internal_observation, internal_verification = _run_internal_iterations(
            research_question,
            toolbox,
            workspace,
            top_k=options.top_k,
            max_iterations=options.max_internal_iterations,
        )

    web_observation: WebSearchObservation | None = None
    if _should_use_web(route, internal_observation, internal_verification):
        _emit_progress(progress_callback, "web_search", "Searching the web...")
        workspace.add_step(
            phase="act",
            decision="use_web_search",
            reason=_web_reason(route, internal_observation, internal_verification),
            tool="web_search",
            observation={"query": research_question, "max_results": options.max_web_results},
        )
        web_observation = toolbox.web_search(research_question, max_results=options.max_web_results)
        workspace.add_step(
            phase="observe",
            decision="inspect_web_evidence",
            reason="Web search returned public evidence or a recoverable tool error.",
            tool="web_search",
            observation=web_observation.summary(),
        )
        if options.remember_web_results and web_observation.results:
            memory_stats = remember_web_results(db_path, question=research_question, results=web_observation.results)
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
    _emit_progress(progress_callback, "writing", "Writing the answer...")
    response = _synthesize_response(
        question,
        research_question,
        results,
        web_results,
        assessment,
        route,
        workspace,
        llm,
        combined_history,
        web_error,
    )
    _log_query(db_path, question, response, telemetry_session_id=telemetry_session_id)
    return response


def _emit_progress(
    callback: Callable[[dict[str, Any]], None] | None,
    stage: str,
    message: str,
    **metadata: Any,
) -> None:
    if not callback:
        return
    callback({"type": "progress", "stage": stage, "message": message, **metadata})


def _route_status_message(route: RouteDecision) -> str:
    if route.intent == "chat_summary":
        return "Reading this chat..."
    if route.needs_research:
        return "Planning the research path..."
    return "Preparing a reply..."


def _direct_status_message(route: RouteDecision) -> str:
    if route.intent == "chat_summary":
        return "Summarizing the chat..."
    if route.needs_clarification:
        return "Writing a clarification..."
    return "Writing a reply..."


def _combined_chat_history(
    db_path: str | Path,
    *,
    telemetry_session_id: str | None,
    supplied_history: list[dict[str, str]],
    current_question: str,
) -> list[dict[str, str]]:
    stored = load_chat_history(db_path, telemetry_session_id, limit=14)
    merged: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in [*stored, *supplied_history]:
        role = str(item.get("role") or "").strip()
        content = " ".join(str(item.get("content") or "").split())
        if role not in {"user", "assistant"} or not content:
            continue
        if role == "user" and content == " ".join(current_question.split()):
            continue
        key = (role, content)
        if key in seen:
            continue
        merged.append({"role": role, "content": content[:1600]})
        seen.add(key)
    return merged[-14:]


def _route_with_reasoner(
    question: str,
    *,
    use_web_fallback: bool,
    llm: LLMProvider,
    chat_history: list[dict[str, str]],
) -> tuple[RouteDecision, str]:
    deterministic = route_message(question, use_web_fallback=use_web_fallback)
    if _is_memory_follow_up(question, chat_history):
        deterministic = RouteDecision(
            intent="external_research",
            needs_research=True,
            allow_internal_search=True,
            allow_web_search=use_web_fallback,
            needs_clarification=False,
            reason="The message is a follow-up to the current chat topic.",
            constraints=["Resolve the topic from chat memory before retrieval."],
        )
    if deterministic.intent in {"chat_summary", "system_help"}:
        return deterministic, "deterministic_guardrail"
    if not llm.is_configured:
        return deterministic, "deterministic"

    try:
        payload = llm.complete_json(
            [
                {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": routing_prompt(
                        question,
                        use_web_fallback=use_web_fallback,
                        chat_history=chat_history,
                    ),
                },
            ],
            reasoning=True,
        )
        reasoned = _route_from_payload(payload, use_web_fallback=use_web_fallback)
    except RuntimeError:
        return deterministic, "deterministic"

    if deterministic.needs_research and not reasoned.needs_research:
        return deterministic, "deterministic_guardrail"
    if deterministic.intent in {"current_research", "external_research"} and reasoned.intent == "internal_research":
        return deterministic, "deterministic_guardrail"
    if reasoned.needs_research and not deterministic.needs_research:
        return reasoned, "deepseek_reasoner"
    if deterministic.needs_research and reasoned.needs_research:
        return reasoned, "deepseek_reasoner"
    return reasoned, "deepseek_reasoner"


def _route_from_payload(payload: dict[str, Any], *, use_web_fallback: bool) -> RouteDecision:
    intent = str(payload.get("intent") or "clarification_needed").strip()
    valid_intents = {
        "casual_chat",
        "chat_summary",
        "system_help",
        "clarification_needed",
        "internal_research",
        "current_research",
        "external_research",
    }
    if intent not in valid_intents:
        intent = "clarification_needed"

    needs_research = intent in {"internal_research", "current_research", "external_research"} or bool(
        payload.get("needs_research")
    )
    allow_internal = needs_research and bool(payload.get("allow_internal_search", True))
    allow_web = needs_research and use_web_fallback and bool(payload.get("allow_web_search", use_web_fallback))
    needs_clarification = intent == "clarification_needed" or bool(payload.get("needs_clarification"))
    constraints = payload.get("constraints")
    if not isinstance(constraints, list):
        constraints = []

    return RouteDecision(
        intent=intent,
        needs_research=needs_research,
        allow_internal_search=allow_internal,
        allow_web_search=allow_web,
        needs_clarification=needs_clarification,
        reason=str(payload.get("reason") or "DeepSeek reasoner classified the message."),
        constraints=[str(item) for item in constraints[:4]],
    )


def _standalone_research_question(
    question: str,
    chat_history: list[dict[str, str]],
    llm: LLMProvider,
    workspace: ResearchWorkspace,
) -> str:
    if not chat_history:
        return question

    fallback = _fallback_standalone_question(question, chat_history)
    if _is_memory_follow_up(question, chat_history):
        workspace.add_step(
            phase="plan",
            decision="contextualize_question",
            reason="The user asked a short follow-up, so the controller resolved the topic from chat memory before searching.",
            observation={"standalone_question": fallback, "context_source": "deterministic_follow_up"},
        )
        return fallback
    if not llm.is_configured:
        workspace.add_step(
            phase="plan",
            decision="contextualize_question",
            reason="Recent chat memory was available, so the controller built a standalone search question.",
            observation={"standalone_question": fallback, "context_source": "deterministic"},
        )
        return fallback

    try:
        payload = llm.complete_json(
            [
                {"role": "system", "content": CONTEXTUALIZE_SYSTEM_PROMPT},
                {"role": "user", "content": contextualize_prompt(question, chat_history)},
            ],
            reasoning=True,
        )
        standalone = str(payload.get("standalone_question") or "").strip() or fallback
    except RuntimeError:
        standalone = fallback

    workspace.add_step(
        phase="plan",
        decision="contextualize_question",
        reason="Recent chat memory was available, so the controller built a standalone search question.",
        observation={"standalone_question": standalone},
    )
    return standalone


def _fallback_standalone_question(question: str, chat_history: list[dict[str, str]]) -> str:
    lowered = question.lower()
    topic = _recent_chat_topic(chat_history)
    if _is_memory_follow_up(question, chat_history) and topic:
        return f"{question} about {topic}"
    if any(token in lowered for token in (" it", " this", " that", " them", " those", "same", "more", "compare")):
        previous = _previous_user_question(chat_history)
        if previous:
            return f"{question} Context from previous user question: {previous}"
    return question


def _is_memory_follow_up(question: str, chat_history: list[dict[str, str]]) -> bool:
    if not chat_history:
        return False
    lowered = " ".join(question.lower().split())
    compact = lowered.strip(" ?!.")
    follow_up_patterns = (
        r"^(can|could|would) you (tell me|explain|give me) more$",
        r"^(tell me|explain|give me) more$",
        r"^more$",
        r"^what else$",
        r"^go deeper$",
        r"^expand on (that|this|it)$",
        r"^what about (this|that|it)\b",
    )
    return any(re.search(pattern, compact) for pattern in follow_up_patterns)


def _recent_chat_topic(chat_history: list[dict[str, str]]) -> str | None:
    for item in reversed(chat_history):
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        topic = _topic_from_text(content)
        if topic:
            return topic
    previous = _previous_user_question(chat_history)
    return previous


def _topic_from_text(text: str) -> str | None:
    patterns = (
        r"\b(T[-\s]?Hub)\b(?:[^.]{0,40}\bHyderabad\b)?",
        r"\b(AIC T[-\s]?Hub)\b",
        r"\b(Hong Kong startup grants?)\b",
        r"\b(Shenzhen startup grants?)\b",
        r"\b([A-Z][A-Za-z0-9&.\- ]{1,40}(?:Hub|Park|Programme|Program|Fund|Grant|Center|Centre|Incubator))\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            topic = " ".join(match.group(1).replace("\n", " ").split())
            if topic.lower() == "t hub":
                topic = "T-Hub in Hyderabad"
            return topic
    return None


def _previous_user_question(chat_history: list[dict[str, str]]) -> str | None:
    for item in reversed(chat_history):
        if item.get("role") == "user":
            previous = str(item.get("content") or "").strip()
            if previous:
                return previous
    return None


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
    evidence_question: str,
    results: list[RetrievalResult],
    web_results: list[WebResult],
    assessment: EvidenceAssessment | None,
    route: RouteDecision,
    workspace: ResearchWorkspace,
    llm: LLMProvider,
    chat_history: list[dict[str, str]],
    web_error: str | None,
) -> dict[str, Any]:
    verified = verify_evidence(evidence_question, results, assessment, web_results)
    accepted_results = verified.accepted_internal
    accepted_web_results = verified.accepted_web
    source_mode = _source_mode(accepted_results, accepted_web_results)
    answer_results, answer_web_results = _select_answer_evidence(accepted_results, accepted_web_results)
    citations = [*unique_citations(answer_results), *unique_web_citations(answer_web_results)]
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
            evidence_question,
            answer_results,
            answer_web_results,
            confidence,
            gaps,
            source_mode,
            llm,
            chat_history,
        )
        response["citations"] = citations
        response["confidence"] = confidence
        response.setdefault("gaps", gaps)
    else:
        response = _extractive_answer(answer_results, answer_web_results, confidence, source_mode, citations, gaps)

    response["source_mode"] = source_mode if citations else "insufficient"
    response["used_web_fallback"] = bool(web_results or web_error)
    response["retrieved_evidence"] = [_evidence_payload(result) for result in accepted_results]
    response["web_evidence"] = [_web_payload(result) for result in accepted_web_results]
    response["rejected_evidence"] = verified.rejected_internal
    response["route"] = route.as_dict()
    response["reasoning_trace"] = workspace.trace()
    return response


def _select_answer_evidence(
    internal_results: list[RetrievalResult],
    web_results: list[WebResult],
) -> tuple[list[RetrievalResult], list[WebResult]]:
    if internal_results and web_results:
        return internal_results[:1], web_results[:3]
    if internal_results:
        return internal_results[:4], []
    if web_results:
        return [], web_results[:4]
    return [], []


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
        context_parts.append("Sources:\n" + results_to_context(results, start_index=1))
    if web_results:
        context_parts.append("Sources:\n" + web_results_to_context(web_results, start_index=len(results) + 1))
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
        answer = "\n".join(points)
    else:
        answer = "I do not have enough clean source text to answer that well yet."

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
        agent_name="reasoning_agent",
        session_external_id=telemetry_session_id,
    )
