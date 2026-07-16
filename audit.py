import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from embedding_client import semantic_matches, similarity_to_score, split_criteria, split_text

DEFAULT_LOG_FILE = Path(__file__).resolve().parent / "audit_log.jsonl"
LOG_FILE = Path(os.getenv("AUDIT_LOG_FILE", str(DEFAULT_LOG_FILE))).expanduser().resolve()
_LOG_LOCK = Lock()


def _sha256_text(value: str) -> str:
    """Returns a stable SHA-256 fingerprint without storing proposal content."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _validate_required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")
    return value.strip()


def _validate_score_result(score_result: dict[str, Any]) -> tuple[int, str]:
    if not isinstance(score_result, dict):
        raise TypeError("score_result must be a dictionary.")

    score = score_result.get("score")
    reasoning = score_result.get("reasoning")

    if isinstance(score, bool) or not isinstance(score, int):
        raise ValueError("score_result['score'] must be an integer.")
    if not 0 <= score <= 100:
        raise ValueError("score_result['score'] must be between 0 and 100.")
    if not isinstance(reasoning, str) or not reasoning.strip():
        raise ValueError("score_result['reasoning'] must be a non-empty string.")

    return score, reasoning.strip()


def _check_consistency(
    vendor_text: str,
    rfp_criteria: str,
    score: int,
    reasoning: str,
) -> dict[str, Any]:
    """Recompute semantic fit and verify that the stored score is reproducible."""
    criteria = split_criteria(rfp_criteria)
    passages = split_text(vendor_text)
    matches = semantic_matches(criteria, passages, top_k=1)
    expected_score = round(
        sum(similarity_to_score(result[0]["relevance"]) for result in matches)
        / len(matches)
    )
    difference = abs(expected_score - score)
    consistent = difference <= 2 and "Semantic evidence matches:" in reasoning
    concern = "" if consistent else (
        f"Stored score differs from the recomputed semantic score by {difference} points."
    )
    return {"consistent": consistent, "concern": concern}


def audit_vendor_score(
    vendor_name: str,
    vendor_text: str,
    rfp_criteria: str,
    score_result: dict[str, Any],
) -> dict[str, Any]:
    """Creates and persists an auditable record for one vendor evaluation."""
    vendor_name = _validate_required_text(vendor_name, "vendor_name")
    vendor_text = _validate_required_text(vendor_text, "vendor_text")
    rfp_criteria = _validate_required_text(rfp_criteria, "rfp_criteria")
    score, reasoning = _validate_score_result(score_result)

    try:
        check = _check_consistency(vendor_text, rfp_criteria, score, reasoning)
        consistency_error = ""
    except (RuntimeError, TypeError, ValueError) as exc:
        # Preserve the original score while making it explicit that the
        # independent verification step did not complete successfully.
        check = {"consistent": None, "concern": "Consistency check failed."}
        consistency_error = str(exc)

    record: dict[str, Any] = {
        "audit_id": str(uuid4()),
        "vendor_name": vendor_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "score": score,
        "reasoning": reasoning,
        "criteria_results": score_result.get("criteria_results", []),
        "rfp_criteria": rfp_criteria,
        "vendor_text_sha256": _sha256_text(vendor_text),
        "rfp_criteria_sha256": _sha256_text(rfp_criteria),
        "consistent": check["consistent"],
        "concern": check["concern"],
        "consistency_error": consistency_error,
    }

    _append_to_log(record)
    return record


def _append_to_log(record: dict[str, Any]) -> None:
    """Atomically appends one UTF-8 JSON record within the current process."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(record, ensure_ascii=False, separators=(",", ":"))

    with _LOG_LOCK:
        with LOG_FILE.open("a", encoding="utf-8", newline="\n") as file:
            file.write(serialized + "\n")
            file.flush()
            os.fsync(file.fileno())


def get_audit_trail(
    vendor_name: str | None = None,
    *,
    offset: int = 0,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return a bounded, newest-first page of audit records."""
    if vendor_name is not None:
        vendor_name = _validate_required_text(vendor_name, "vendor_name")

    if not LOG_FILE.exists():
        return []

    records: list[dict[str, Any]] = []
    with _LOG_LOCK:
        with LOG_FILE.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                if not line.strip():
                    continue

                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        f"Invalid JSON in audit log at line {line_number}."
                    ) from exc

                if not isinstance(record, dict):
                    raise RuntimeError(
                        f"Invalid audit record at line {line_number}: expected an object."
                    )

                if vendor_name is None or record.get("vendor_name") == vendor_name:
                    records.append(record)

    records.reverse()
    return records[offset : offset + limit]
