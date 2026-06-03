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
                "You are the Venture Metrics assistant. Summarize the chat so far in plain language. "
                "Do not cite sources, mention tools, or add new facts. Return JSON with key answer."
                if intent == "chat_summary"
                else (
                    "You are the Venture Metrics assistant. Reply naturally and briefly to casual chat. "
                    "Do not cite sources, mention tools, mention hidden routing, or push the user into a fixed script. "
                    "If useful, invite the next message in a normal conversational way. Return JSON with key answer."
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
            "I am the Venture Metrics research assistant. I can keep a chat session, use the indexed source library first, search the web when evidence is missing, and answer with citations and confidence."
        )
    if compact in {"thanks", "thank you", "谢谢", "謝謝"}:
        return "No problem."
    if "how are you" in lowered or "how is it going" in lowered or "how's it going" in lowered:
        return "I am running normally."
    if compact in {"ok", "okay", "cool"}:
        return "Got it."
    return "Hi."
