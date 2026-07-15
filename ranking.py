from typing import Any


def rank_vendors(vendor_scores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """vendor_scores: list of {"name": str, "score": int, "reasoning": str}"""
    if not isinstance(vendor_scores, list):
        raise TypeError("vendor_scores must be a list.")

    for index, vendor in enumerate(vendor_scores):
        if not isinstance(vendor, dict):
            raise ValueError(f"Vendor at index {index} must be an object.")
        if not isinstance(vendor.get("name"), str) or not vendor["name"].strip():
            raise ValueError(f"Vendor at index {index} must have a non-empty name.")
        score = vendor.get("score")
        if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
            raise ValueError(f"Vendor at index {index} must have a score from 0 to 100.")
        if not isinstance(vendor.get("reasoning"), str):
            raise ValueError(f"Vendor at index {index} must have string reasoning.")

    return sorted(vendor_scores, key=lambda v: v["score"], reverse=True)
