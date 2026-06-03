"""Intent routing for the reasoning controller."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


RESEARCH_TERMS = (
    "source",
    "sources",
    "data",
    "evidence",
    "funding",
    "grant",
    "programme",
    "program",
    "policy",
    "startup",
    "entrepreneur",
    "incubator",
    "science park",
    "university",
    "spin-off",
    "spinoff",
    "gba",
    "hong kong",
    "shenzhen",
    "compare",
    "find",
    "mention",
    "mentions",
    "list",
    "official",
    "government",
    "香港",
    "深圳",
    "大湾区",
    "创业",
    "創業",
    "资助",
    "資助",
    "政策",
)
CURRENT_TERMS = (
    "latest",
    "current",
    "today",
    "this week",
    "recent",
    "now",
    "2026",
    "最新",
    "目前",
    "本周",
    "今年",
)
WEB_TERMS = (
    "web",
    "internet",
    "online",
    "public web",
    "search the web",
    "look up",
    "google",
    "查一下",
    "网上",
    "網上",
)
HELP_PATTERNS = (
    r"\bwhat can you do\b",
    r"\bhow do you work\b",
    r"\bhelp\b",
    r"\bintroduce yourself\b",
    r"\bgive me your intro(duction)?\b",
    r"\bwhat data (do you|is)\b",
    r"\bwho are you\b",
    r"\bwhat are you\b",
    r"\bwhat('?s| is) your name\b",
)
SOCIAL_PATTERNS = (
    r"\bhow are you\b",
    r"\bhow('?s| is) it going\b",
    r"\bhow are things\b",
    r"\bwhat('?s| is) up\b",
    r"\bgood morning\b",
    r"\bgood afternoon\b",
    r"\bgood evening\b",
)
SUMMARY_PATTERNS = (
    r"\bsummarize (this|our|the) chat\b",
    r"\bsummarise (this|our|the) chat\b",
    r"\bsummarize (this|our|the) conversation\b",
    r"\bsummarise (this|our|the) conversation\b",
    r"\brecap (this|our|the) chat\b",
    r"\brecap (this|our|the) conversation\b",
)
FACTUAL_START_PATTERNS = (
    r"\bwhat('?s| is| are)\b",
    r"\bwhat about\b",
    r"\bwhere (is|are|can|do|does)\b",
    r"\bwho (is|are|runs|founded)\b",
    r"\bwhich\b",
    r"\bwhen\b",
    r"\bwhy\b",
    r"\bhow (does|do|can|to|is|are)\b",
    r"\btell me about\b",
    r"\bexplain\b",
    r"\bdefine\b",
    r"\bcompare\b",
)


@dataclass(frozen=True)
class RouteDecision:
    intent: str
    needs_research: bool
    allow_internal_search: bool
    allow_web_search: bool
    needs_clarification: bool
    reason: str
    constraints: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "intent": self.intent,
            "needs_research": self.needs_research,
            "allow_internal_search": self.allow_internal_search,
            "allow_web_search": self.allow_web_search,
            "needs_clarification": self.needs_clarification,
            "reason": self.reason,
            "constraints": self.constraints,
        }


def route_message(question: str, *, use_web_fallback: bool = True) -> RouteDecision:
    text = " ".join(question.strip().split())
    lowered = text.lower()

    if not text:
        return RouteDecision(
            intent="clarification_needed",
            needs_research=False,
            allow_internal_search=False,
            allow_web_search=False,
            needs_clarification=True,
            reason="The message is empty.",
        )

    if _is_casual_chat(lowered) and not _looks_like_factual_question(lowered):
        return RouteDecision(
            intent="casual_chat",
            needs_research=False,
            allow_internal_search=False,
            allow_web_search=False,
            needs_clarification=False,
            reason="The message is conversational and does not ask for research.",
        )

    if any(re.search(pattern, lowered) for pattern in SUMMARY_PATTERNS):
        return RouteDecision(
            intent="chat_summary",
            needs_research=False,
            allow_internal_search=False,
            allow_web_search=False,
            needs_clarification=False,
            reason="The user asked to summarize the current chat session, not external evidence.",
        )

    if any(re.search(pattern, lowered) for pattern in HELP_PATTERNS):
        return RouteDecision(
            intent="system_help",
            needs_research=False,
            allow_internal_search=False,
            allow_web_search=False,
            needs_clarification=False,
            reason="The user is asking about system capabilities rather than source evidence.",
        )

    if _is_too_vague(lowered):
        return RouteDecision(
            intent="clarification_needed",
            needs_research=False,
            allow_internal_search=False,
            allow_web_search=False,
            needs_clarification=True,
            reason="The message is too vague to select useful tools.",
        )

    asks_current = _contains_any(lowered, CURRENT_TERMS)
    asks_web = _contains_any(lowered, WEB_TERMS)
    looks_research = _contains_any(lowered, RESEARCH_TERMS)
    looks_factual = _looks_like_factual_question(lowered)

    if asks_current or asks_web:
        return RouteDecision(
            intent="current_research" if asks_current else "external_research",
            needs_research=True,
            allow_internal_search=True,
            allow_web_search=use_web_fallback,
            needs_clarification=False,
            reason="The user asked for current or external verification.",
            constraints=["Prefer internal evidence first when relevant.", "Use web only as a controlled tool."],
        )

    if looks_research or looks_factual:
        return RouteDecision(
            intent="internal_research" if looks_research else "external_research",
            needs_research=True,
            allow_internal_search=True,
            allow_web_search=use_web_fallback,
            needs_clarification=False,
            reason=(
                "The message asks a research-style question that may be answerable from indexed sources."
                if looks_research
                else "The message asks a factual question and should not be handled as casual chat."
            ),
            constraints=["Start with local indexed evidence.", "Escalate only if evidence is weak or missing."],
        )

    return RouteDecision(
        intent="casual_chat",
        needs_research=False,
        allow_internal_search=False,
        allow_web_search=False,
        needs_clarification=False,
        reason="No research intent was detected.",
    )


def asks_for_current_data(question: str) -> bool:
    return _contains_any(question.lower(), CURRENT_TERMS)


def _is_casual_chat(lowered: str) -> bool:
    compact = re.sub(r"[^\w\u4e00-\u9fff]+", " ", lowered).strip()
    if any(re.search(pattern, lowered) for pattern in SOCIAL_PATTERNS):
        return True

    casual = {
        "hi",
        "hello",
        "hey",
        "yo",
        "sup",
        "thanks",
        "thank you",
        "ok",
        "okay",
        "cool",
        "你好",
        "谢谢",
        "謝謝",
    }
    return compact in casual or bool(re.fullmatch(r"(hi|hello|hey|yo)[.! ]*", lowered))


def _is_too_vague(lowered: str) -> bool:
    compact = re.sub(r"[^\w\u4e00-\u9fff]+", " ", lowered).strip()
    vague = {"tell me more", "explain", "research this", "find this", "more", "why", "how"}
    return compact in vague


def _looks_like_factual_question(lowered: str) -> bool:
    if any(re.search(pattern, lowered) for pattern in SOCIAL_PATTERNS):
        return False
    if any(re.search(pattern, lowered) for pattern in SUMMARY_PATTERNS):
        return False
    if any(re.search(pattern, lowered) for pattern in HELP_PATTERNS):
        return False
    if any(re.search(pattern, lowered) for pattern in FACTUAL_START_PATTERNS):
        return True
    if "?" in lowered and len(lowered.split()) >= 4:
        return True
    return False


def _contains_any(lowered: str, terms: tuple[str, ...]) -> bool:
    return any(term in lowered for term in terms)
