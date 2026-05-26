"""Planning helpers for reasoning internal search iterations."""

from __future__ import annotations

import re

from venture_metrics_agent.reasoning.verifier import VerifiedEvidence, query_terms_for_question


REGION_EXPANSIONS = {
    "hong": "Hong Kong",
    "kong": "Hong Kong",
    "hk": "Hong Kong",
    "香港": "Hong Kong 香港",
    "shenzhen": "Shenzhen",
    "深圳": "Shenzhen 深圳",
    "gba": "Greater Bay Area GBA",
    "greater": "Greater Bay Area GBA",
    "bay": "Greater Bay Area GBA",
    "大湾区": "Greater Bay Area GBA 大湾区",
}
TOPIC_EXPANSIONS = {
    "funding": "funding grant fund scheme programme support",
    "grant": "grant funding scheme programme subsidy",
    "startup": "startup start-up entrepreneurship venture incubat",
    "entrepreneurship": "entrepreneurship startup incubation competition mentorship funding",
    "incubator": "incubator incubation accelerator science park",
    "policy": "policy programme scheme government support",
    "university": "university knowledge transfer entrepreneurship centre innovation",
}


def internal_search_queries(question: str, *, max_queries: int = 3) -> list[str]:
    terms = query_terms_for_question(question)
    queries = [question]

    expanded_parts: list[str] = []
    for term in terms:
        if term in REGION_EXPANSIONS:
            expanded_parts.append(REGION_EXPANSIONS[term])
        elif term in TOPIC_EXPANSIONS:
            expanded_parts.append(TOPIC_EXPANSIONS[term])
        else:
            expanded_parts.append(term)
    expanded = " ".join(expanded_parts)
    if expanded and _normalized(expanded) != _normalized(question):
        queries.append(expanded)

    compact = " ".join(term for term in terms if term not in {"source", "sources"})
    if compact and _normalized(compact) not in {_normalized(query) for query in queries}:
        queries.append(compact)

    return queries[:max_queries]


def should_refine_internal_search(verification: VerifiedEvidence, *, iteration: int, max_iterations: int) -> bool:
    if iteration >= max_iterations:
        return False
    if not verification.answerable:
        return True
    if verification.confidence in {"Low", "Insufficient evidence"}:
        return True
    return False


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()
