"""Casual response helpers for the reasoning controller."""

from __future__ import annotations

import hashlib
import re

from venture_metrics_agent.llm.provider import LLMProvider


GREETINGS = (
    "Hey. What are we working through today?",
    "Hi. I am here. Ask normally, or give me a research question when you want sources.",
    "Hello. What should we look into?",
)
SOCIAL_REPLIES = (
    "I am good. Ready to help you think through the Venture Metrics work or just talk through the next step.",
    "Doing fine. What do you want to tackle next?",
    "I am here and ready. What are we looking at?",
)


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
            response = llm.complete_json(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are the Venture Metrics assistant. Reply naturally and briefly to casual chat. "
                            "Do not cite sources, mention tools, mention hidden routing, or push the user into a fixed script. "
                            "If useful, invite the next message in a normal conversational way. Return JSON with key answer."
                        ),
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

    return _fallback_response(question, intent=intent)


def _fallback_response(question: str, *, intent: str) -> str:
    lowered = question.lower().strip()
    compact = re.sub(r"[^\w\u4e00-\u9fff]+", " ", lowered).strip()

    if intent == "system_help":
        return (
            "I can chat normally, help reason through the project, and answer Venture Metrics research questions "
            "with cited evidence when the question needs sources."
        )
    if compact in {"thanks", "thank you", "谢谢", "謝謝"}:
        return "No problem."
    if "how are you" in lowered or "how is it going" in lowered or "how's it going" in lowered:
        return _pick(SOCIAL_REPLIES, lowered)
    if compact in {"ok", "okay", "cool"}:
        return "Got it."
    return _pick(GREETINGS, lowered)


def _pick(options: tuple[str, ...], seed: str) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return options[int(digest[:8], 16) % len(options)]
