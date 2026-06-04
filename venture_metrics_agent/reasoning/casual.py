"""Casual response helpers for the reasoning controller."""

from __future__ import annotations

import re

from venture_metrics_agent.llm.provider import LLMProvider


def casual_response(
    question: str,
    *,
    intent: str,
    chat_history: list[dict[str, str]],
    llm: LLMProvider,
) -> str:
    """Return a short non-retrieval response for conversational turns."""

    if llm.is_configured:
        try:
            system_content = (
                "You are Venture Metrics. Summarize the chat so far in plain language. "
                "Do not cite sources, mention tools, or add new facts. Return JSON with key answer."
                if intent == "chat_summary"
                else (
                    "You are Venture Metrics, a chat-first research assistant for entrepreneurship ecosystem data. "
                    "Reply naturally and briefly. "
                    "Sound warm, attentive, and project-aware, not robotic. If the user gives feedback, acknowledge "
                    "it and adjust. Do not cite sources, mention tools, mention hidden routing, or push the user "
                    "into a fixed script. Return JSON with key answer."
                )
            )
            response = llm.complete_json(
                [
                    {
                        "role": "system",
                        "content": system_content,
                    },
                    *chat_history[-6:],
                    {"role": "user", "content": question},
                ],
                temperature=0.7,
            )
            answer = str(response.get("answer") or "").strip()
            if answer:
                return answer
        except RuntimeError:
            pass

    return _fallback_response(question, intent=intent, chat_history=chat_history)


def _fallback_response(question: str, *, intent: str, chat_history: list[dict[str, str]]) -> str:
    lowered = question.lower().strip()
    compact = re.sub(r"[^\w\u4e00-\u9fff]+", " ", lowered).strip()

    if intent == "chat_summary":
        recent = [item for item in chat_history if item.get("role") in {"user", "assistant"}][-6:]
        if not recent:
            return "This chat has just started."
        return "So far, we discussed: " + " ".join(
            str(item.get("content") or "").strip().split(".")[0] for item in recent if item.get("content")
        )
    if intent == "system_help":
        return (
            "I am Venture Metrics. I help explore entrepreneurship sources, policies, funding, incubators, universities, and benchmark ecosystems. For research questions, I use the saved source library first and add citations when I answer."
        )
    if compact in {"thanks", "thank you", "谢谢", "謝謝"}:
        return "No problem."
    if "nice to meet you" in lowered or "good to meet you" in lowered or "pleased to meet you" in lowered:
        return "Nice to meet you too. I can help with source exploration, entrepreneurship research, or just talk through what you are testing."
    if "how are you" in lowered or "how is it going" in lowered or "how's it going" in lowered:
        return "I am doing well. Ready to help with the source library or talk through what you are testing."
    if _looks_like_feedback(lowered):
        return "Fair point. That sounded too mechanical. I will keep casual replies more natural and save the research mode for questions that actually need sources."
    if compact in {"ok", "okay", "cool"}:
        return "Got it."
    if compact in {"hi", "hello", "hey", "yo", "你好"}:
        return "Hi. What are you working on today?"
    return "I am here. Tell me what you want to explore or test next."


def _looks_like_feedback(lowered: str) -> bool:
    return any(
        phrase in lowered
        for phrase in (
            "artificial",
            "robotic",
            "awkward",
            "bad response",
            "wrong response",
            "not helpful",
            "not what i asked",
            "not what i meant",
            "misunderstood",
        )
    )
