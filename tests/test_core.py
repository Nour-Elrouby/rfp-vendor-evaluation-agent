import json

import audit
import chatbot
from reader import validate_file_signature


def test_chat_sends_only_retrieved_evidence(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        chatbot,
        "split_text",
        lambda text, max_chars=500: ["timeline evidence", "private appendix"],
    )
    monkeypatch.setattr(
        chatbot,
        "semantic_matches",
        lambda queries, passages, top_k=4: [
            [{"text": "timeline evidence", "similarity": 0.9}]
        ],
    )

    def fake_generate(prompt):
        captured["prompt"] = prompt
        return {"answer": "Implementation takes 16 weeks."}

    monkeypatch.setattr(chatbot, "generate_json", fake_generate)
    answer = chatbot.answer_question("What is the timeline?", "FULL_RFP")

    assert answer == "Implementation takes 16 weeks."
    assert "timeline evidence" in captured["prompt"]
    assert "FULL_RFP" not in captured["prompt"]
    assert "private appendix" not in captured["prompt"]


def test_audit_pagination_is_newest_first(tmp_path, monkeypatch):
    log_file = tmp_path / "audit.jsonl"
    records = [{"audit_id": str(index), "vendor_name": "Vendor"} for index in range(5)]
    log_file.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(audit, "LOG_FILE", log_file)

    page = audit.get_audit_trail(offset=1, limit=2)
    assert [record["audit_id"] for record in page] == ["3", "2"]


def test_file_signature_validation():
    validate_file_signature(b"%PDF-1.7", ".pdf")
    validate_file_signature(b"PK\x03\x04", ".docx")

    try:
        validate_file_signature(b"plain text", ".pdf")
    except ValueError as exc:
        assert "valid PDF" in str(exc)
    else:
        raise AssertionError("Fake PDF was accepted.")
