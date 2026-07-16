from typing import Any

from embedding_client import semantic_matches, similarity_to_score, split_criteria, split_text


def _excerpt(text: str, limit: int = 220) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def score_vendor(vendor_text: str, rfp_criteria: str) -> dict[str, Any]:
    """Score each RFP criterion against its closest proposal evidence."""
    if not isinstance(vendor_text, str) or not vendor_text.strip():
        raise ValueError("vendor_text must be a non-empty string.")
    if not isinstance(rfp_criteria, str) or not rfp_criteria.strip():
        raise ValueError("rfp_criteria must be a non-empty string.")

    criteria = split_criteria(rfp_criteria)
    passages = split_text(vendor_text)
    matches = semantic_matches(criteria, passages, top_k=1)

    criterion_results: list[dict[str, Any]] = []
    for criterion, result in zip(criteria, matches):
        best = result[0]
        criterion_results.append(
            {
                "criterion": criterion,
                "evidence": best["text"],
                "similarity": round(best["similarity"], 4),
                "score": similarity_to_score(best["similarity"]),
            }
        )

    score = round(
        sum(item["score"] for item in criterion_results) / len(criterion_results)
    )
    strongest = sorted(criterion_results, key=lambda item: item["score"], reverse=True)[:3]
    weakest = min(criterion_results, key=lambda item: item["score"])

    evidence_summary = "; ".join(
        f"{item['criterion']} -> {_excerpt(item['evidence'])} ({item['score']}%)"
        for item in strongest
    )
    reasoning = f"Semantic evidence matches: {evidence_summary}."
    if weakest["score"] < 45:
        reasoning += (
            f" Weakest match: {weakest['criterion']} "
            f"({weakest['score']}% similarity-based fit)."
        )

    return {
        "score": score,
        "reasoning": reasoning,
        "criteria_results": criterion_results,
    }
