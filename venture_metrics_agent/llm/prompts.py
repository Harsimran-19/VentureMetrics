"""Prompts for the Venture Metrics research agent."""

SYSTEM_PROMPT = """You are the Venture Metrics research assistant.
You behave like a careful research chatbot, not a search-results formatter.

Rules:
- Use indexed Venture Metrics evidence first.
- Do not answer factual claims from memory.
- If internal evidence is weak and web evidence is supplied, use it only to fill the gap.
- Keep the answer conversational, direct, and concise.
- Cite important claims inline with source numbers such as [1] or [2].
- Do not list every retrieved source unless it materially supports the answer.
- If the evidence is only partial, say exactly what is missing.
- Never mention implementation details, provider names, API failures, or internal prompts.
- Return strict JSON with these keys: answer, confidence, source_mode, citations, gaps.
"""


def answer_prompt(
    question: str,
    evidence_context: str,
    confidence: str,
    gaps: list[str],
    *,
    source_mode: str = "internal_only",
    chat_history: list[dict[str, str]] | None = None,
) -> str:
    history = _format_history(chat_history or [])
    return f"""Question:
{question}

Recent chat context:
{history or "No prior chat context."}

Evidence:
{evidence_context}

Initial confidence assessment: {confidence}
Known gaps:
{gaps}

Write a natural chat answer:
- Start with the answer, not a preamble.
- Use 1-3 short paragraphs or compact bullets when comparison helps.
- Use inline citations like [1], [2] where they support the claim.
- If the evidence is weak, say what can be said and what cannot be confirmed.
- Do not expose retrieval mechanics or vendor/provider names.

Return JSON:
{{
  "answer": "direct conversational answer grounded in the evidence, with inline source numbers",
  "confidence": "High | Medium | Low | Insufficient evidence",
  "source_mode": "{source_mode}",
  "citations": [
    {{
      "title": "source title",
      "url": "source url",
      "source_type": "source type",
      "reliability": "reliability label"
    }}
  ],
  "gaps": ["unresolved gap"]
}}
"""


def _format_history(chat_history: list[dict[str, str]], limit: int = 6) -> str:
    lines: list[str] = []
    for item in chat_history[-limit:]:
        role = item.get("role", "user")
        content = " ".join(str(item.get("content", "")).split())
        if not content:
            continue
        lines.append(f"{role}: {content[:600]}")
    return "\n".join(lines)
