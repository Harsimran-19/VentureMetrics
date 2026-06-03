"""Retrieval metrics for architecture evaluation.

These metrics are only computed when an eval case provides ground-truth
source IDs or chunk IDs. Cases without retrieval labels are still useful for
smoke/regression checks, but they cannot validate retriever quality.
"""

from __future__ import annotations

from typing import Any


def score_retrieval(
    retrieved_evidence: list[dict[str, Any]],
    *,
    relevant_source_ids: list[int] | None = None,
    relevant_chunk_ids: list[int] | None = None,
    k: int | None = None,
) -> dict[str, Any]:
    relevant_sources = {int(item) for item in relevant_source_ids or []}
    relevant_chunks = {int(item) for item in relevant_chunk_ids or []}
    has_ground_truth = bool(relevant_sources or relevant_chunks)
    limit = k or len(retrieved_evidence)
    top_results = retrieved_evidence[:limit]

    if not has_ground_truth:
        return {
            "has_ground_truth": False,
            "precision_at_k": None,
            "recall_at_k": None,
            "map_at_k": None,
            "mrr_at_k": None,
            "relevant_found": 0,
            "relevant_total": 0,
            "retrieved_count": len(retrieved_evidence),
            "k": limit,
            "matched_source_ids": [],
            "matched_chunk_ids": [],
        }

    relevant_flags: list[bool] = []
    matched_sources: set[int] = set()
    matched_chunks: set[int] = set()

    for result in top_results:
        source_id = _optional_int(result.get("source_id"))
        chunk_id = _optional_int(result.get("chunk_id"))
        source_match = source_id is not None and source_id in relevant_sources
        chunk_match = chunk_id is not None and chunk_id in relevant_chunks
        matched = source_match or chunk_match
        relevant_flags.append(matched)
        if source_match and source_id is not None:
            matched_sources.add(source_id)
        if chunk_match and chunk_id is not None:
            matched_chunks.add(chunk_id)

    relevant_total = len(relevant_chunks) if relevant_chunks else len(relevant_sources)
    relevant_found = len(matched_chunks) if relevant_chunks else len(matched_sources)
    precision = sum(1 for flag in relevant_flags if flag) / limit if limit else 0.0
    recall = relevant_found / relevant_total if relevant_total else 0.0
    average_precision = _average_precision(relevant_flags, relevant_total)
    reciprocal_rank = _reciprocal_rank(relevant_flags)

    return {
        "has_ground_truth": True,
        "precision_at_k": round(precision, 4),
        "recall_at_k": round(recall, 4),
        "map_at_k": round(average_precision, 4),
        "mrr_at_k": round(reciprocal_rank, 4),
        "relevant_found": relevant_found,
        "relevant_total": relevant_total,
        "retrieved_count": len(retrieved_evidence),
        "k": limit,
        "matched_source_ids": sorted(matched_sources),
        "matched_chunk_ids": sorted(matched_chunks),
    }


def _average_precision(relevant_flags: list[bool], relevant_total: int) -> float:
    if not relevant_total:
        return 0.0
    precision_sum = 0.0
    relevant_seen = 0
    for index, is_relevant in enumerate(relevant_flags, start=1):
        if not is_relevant:
            continue
        relevant_seen += 1
        precision_sum += relevant_seen / index
    return precision_sum / relevant_total


def _reciprocal_rank(relevant_flags: list[bool]) -> float:
    for index, is_relevant in enumerate(relevant_flags, start=1):
        if is_relevant:
            return 1 / index
    return 0.0


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
