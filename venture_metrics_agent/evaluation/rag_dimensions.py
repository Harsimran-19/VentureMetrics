"""Deterministic RAG-dimension evaluators.

These checks implement the Decoding AI Q/C/A structure as a stable first layer:

- C|Q: context relevance
- A|C: faithfulness
- A|Q: answer relevance
- C|A: context support
- Q|C: answerability
- Q|A: self-containment

They are intentionally conservative proxies. The report labels them as
deterministic scores, not validated LLM judges. Later, each function can be
replaced or supplemented by a calibrated dimension-specific LLM judge while
keeping the same output schema.
"""

from __future__ import annotations

import re
from typing import Any


STOPWORDS = {
    "about",
    "also",
    "and",
    "answer",
    "are",
    "can",
    "could",
    "data",
    "does",
    "for",
    "from",
    "give",
    "have",
    "including",
    "into",
    "is",
    "latest",
    "list",
    "mention",
    "mentioned",
    "mentions",
    "most",
    "related",
    "relevant",
    "research",
    "source",
    "sources",
    "support",
    "the",
    "this",
    "what",
    "where",
    "which",
    "with",
}
REFUSAL_TERMS = (
    "do not have enough",
    "insufficient",
    "cannot answer",
    "can't answer",
    "not enough reliable evidence",
    "need more evidence",
)


def evaluate_rag_dimensions(case: Any, output: dict[str, Any]) -> dict[str, dict[str, Any]]:
    question = str(getattr(case, "question", "") or "")
    answer = str(output.get("answer") or "")
    retrieved = _as_list(output.get("retrieved_evidence"))
    web = _as_list(output.get("web_evidence"))
    context = _context_text(retrieved, web)
    required_claims = [str(item) for item in getattr(case, "required_claims", []) or []]
    forbidden_claims = [str(item) for item in getattr(case, "forbidden_claims", []) or []]
    unanswerable = bool(getattr(case, "unanswerable", False))
    expected_source_mode = str(getattr(case, "expected_source_mode", "") or "")
    source_mode = str(output.get("source_mode") or "")

    if expected_source_mode == "no_tools" or source_mode == "no_tools":
        return _non_research_scores("This case is not a RAG research task.")

    if unanswerable and (_is_refusal(answer) or source_mode == "insufficient"):
        return _non_research_scores("This case is intentionally unanswerable and the system refused or marked insufficiency.")

    return {
        "context_relevance": _context_relevance(question, context, retrieved, web),
        "faithfulness": _faithfulness(answer, context, forbidden_claims),
        "answer_relevance": _answer_relevance(question, answer, required_claims, unanswerable),
        "context_support": _context_support(answer, context, required_claims, unanswerable),
        "answerability": _answerability(answer, context, output, unanswerable),
        "self_containment": _self_containment(question, answer),
    }


def _non_research_scores(critique: str) -> dict[str, dict[str, Any]]:
    return {
        "context_relevance": _score(1.0, True, critique),
        "faithfulness": _score(1.0, True, critique),
        "answer_relevance": _score(1.0, True, critique),
        "context_support": _score(1.0, True, critique),
        "answerability": _score(1.0, True, critique),
        "self_containment": _score(1.0, True, critique),
    }


def aggregate_rag_score(scores: dict[str, dict[str, Any]]) -> float:
    if not scores:
        return 0.0
    values = [float(score.get("score") or 0.0) for score in scores.values()]
    return round(sum(values) / len(values), 4)


def rag_passed(scores: dict[str, dict[str, Any]], *, threshold: float = 0.65) -> bool:
    if not scores:
        return False
    return all(float(score.get("score") or 0.0) >= threshold for score in scores.values())


def _context_relevance(question: str, context: str, retrieved: list[Any], web: list[Any]) -> dict[str, Any]:
    terms = _terms(question)
    if not terms:
        return _score(1.0, True, "Question has no strong research terms; context relevance is not stressed.")
    if not context.strip():
        return _score(0.0, False, "No retrieved context was available.")
    hits = [term for term in terms if term in context.lower()]
    score = min(1.0, len(hits) / max(3, len(terms)))
    if retrieved or web:
        score = max(score, 0.25)
    return _score(
        score,
        score >= 0.55,
        f"Matched {len(hits)} of {len(terms)} question terms in retrieved context.",
        {"matched_terms": hits[:12], "context_items": len(retrieved) + len(web)},
    )


def _faithfulness(answer: str, context: str, forbidden_claims: list[str]) -> dict[str, Any]:
    if _is_refusal(answer):
        return _score(1.0, True, "The answer refused or disclosed insufficient evidence.")
    if not answer.strip():
        return _score(0.0, False, "No answer was produced.")
    if not context.strip():
        return _score(0.0, False, "The answer contains claims but no context was retrieved.")

    forbidden_hits = [claim for claim in forbidden_claims if claim and claim.lower() in answer.lower()]
    if forbidden_hits:
        return _score(0.0, False, "Answer contains forbidden claim(s).", {"forbidden_claims": forbidden_hits})

    sentences = _answer_sentences(answer)
    if not sentences:
        return _score(0.5, False, "Answer has no clear factual sentence to check.")
    supported = 0
    weak = 0
    context_terms = set(_terms(context, limit=400))
    for sentence in sentences:
        sentence_terms = set(_terms(sentence, limit=40))
        if not sentence_terms:
            weak += 1
            continue
        overlap = len(sentence_terms & context_terms) / max(1, len(sentence_terms))
        if overlap >= 0.35:
            supported += 1
        elif overlap >= 0.18:
            weak += 1
    score = (supported + 0.5 * weak) / len(sentences)
    return _score(
        score,
        score >= 0.65,
        f"{supported} answer sentence(s) were strongly supported; {weak} were weakly supported.",
        {"sentence_count": len(sentences)},
    )


def _answer_relevance(question: str, answer: str, required_claims: list[str], unanswerable: bool) -> dict[str, Any]:
    if unanswerable:
        passed = _is_refusal(answer)
        return _score(1.0 if passed else 0.0, passed, "Unanswerable case should refuse instead of answering.")
    if not answer.strip():
        return _score(0.0, False, "No answer was produced.")

    question_terms = set(_terms(question))
    answer_terms = set(_terms(answer, limit=220))
    overlap = len(question_terms & answer_terms) / max(1, len(question_terms))
    required_hits = [claim for claim in required_claims if claim and claim.lower() in answer.lower()]
    required_score = len(required_hits) / len(required_claims) if required_claims else 1.0
    score = min(1.0, 0.7 * overlap + 0.3 * required_score)
    return _score(
        score,
        score >= 0.55,
        f"Answer matched {len(question_terms & answer_terms)} of {len(question_terms)} key question terms.",
        {"required_claims_hit": required_hits},
    )


def _context_support(answer: str, context: str, required_claims: list[str], unanswerable: bool) -> dict[str, Any]:
    if unanswerable:
        passed = _is_refusal(answer)
        return _score(1.0 if passed else 0.0, passed, "Unanswerable case should not require supporting context.")
    if not context.strip():
        return _score(0.0, False, "No context was available to support the answer.")
    if required_claims:
        hits = [claim for claim in required_claims if claim and claim.lower() in context.lower()]
        score = len(hits) / len(required_claims)
        return _score(
            score,
            score >= 0.7,
            f"Context contained {len(hits)} of {len(required_claims)} required claim(s).",
            {"required_claims_in_context": hits},
        )
    citations = _citation_markers(answer)
    score = 0.8 if citations else 0.55
    return _score(
        score,
        score >= 0.6,
        "Context exists and answer includes citation markers." if citations else "Context exists, but citation support is weak.",
    )


def _answerability(answer: str, context: str, output: dict[str, Any], unanswerable: bool) -> dict[str, Any]:
    source_mode = str(output.get("source_mode") or "")
    confidence = str(output.get("confidence") or "")
    if unanswerable:
        passed = _is_refusal(answer) or source_mode == "insufficient" or confidence == "Insufficient evidence"
        return _score(1.0 if passed else 0.0, passed, "The case is labeled unanswerable; the system should refuse or mark insufficiency.")
    if not context.strip():
        passed = _is_refusal(answer) or source_mode == "insufficient"
        return _score(0.75 if passed else 0.0, passed, "No context was available; answerability depends on refusing safely.")
    over_refusal = _is_refusal(answer) and source_mode != "insufficient"
    return _score(0.3 if over_refusal else 1.0, not over_refusal, "Answerability matched available context.")


def _self_containment(question: str, answer: str) -> dict[str, Any]:
    if _is_refusal(answer):
        return _score(0.85, True, "Refusal/insufficient-evidence answer is self-contained enough.")
    question_terms = _terms(question)
    if not question_terms:
        return _score(1.0, True, "No key question terms required for self-containment.")
    answer_lower = answer.lower()
    important = question_terms[:8]
    hits = [term for term in important if term in answer_lower]
    score = len(hits) / max(1, len(important))
    return _score(score, score >= 0.45, f"Answer includes {len(hits)} of {len(important)} important question terms.")


def _score(score: float, passed: bool, critique: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    label = "pass" if passed else "fail"
    return {
        "score": round(max(0.0, min(1.0, score)), 4),
        "passed": passed,
        "label": label,
        "critique": critique,
        **(extra or {}),
    }


def _context_text(retrieved: list[Any], web: list[Any]) -> str:
    parts: list[str] = []
    for item in [*retrieved, *web]:
        if not isinstance(item, dict):
            continue
        parts.append(str(item.get("title") or ""))
        parts.append(str(item.get("url") or ""))
        parts.append(str(item.get("snippet") or item.get("content") or ""))
    return " ".join(parts)


def _terms(text: str, *, limit: int = 80) -> list[str]:
    raw = re.findall(r"[\w\u4e00-\u9fff]{2,}", text.lower())
    terms: list[str] = []
    for term in raw:
        if term in STOPWORDS:
            continue
        if term not in terms:
            terms.append(term)
        if len(terms) >= limit:
            break
    return terms


def _answer_sentences(answer: str) -> list[str]:
    cleaned = re.sub(r"\[[0-9]+\]", " ", answer)
    candidates = re.split(r"(?<=[.!?。！？])\s+|\n+|(?:^|\n)\s*-\s+", cleaned)
    return [candidate.strip() for candidate in candidates if len(candidate.strip()) >= 45][:12]


def _citation_markers(answer: str) -> list[str]:
    return re.findall(r"\[[0-9]+\]", answer)


def _is_refusal(answer: str) -> bool:
    lowered = answer.lower()
    return any(term in lowered for term in REFUSAL_TERMS)


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
