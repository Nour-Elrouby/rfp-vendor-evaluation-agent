from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_and_security_headers():
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["content-security-policy"].startswith("default-src")


def test_ranking_endpoint():
    response = client.post(
        "/rank-vendors",
        json=[
            {"name": "Vendor B", "score": 70, "reasoning": "Some gaps"},
            {"name": "Vendor A", "score": 90, "reasoning": "Strong fit"},
        ],
    )
    assert response.status_code == 200
    assert [vendor["name"] for vendor in response.json()] == [
        "Vendor A",
        "Vendor B",
    ]


def test_rejects_invalid_rank_payload():
    response = client.post(
        "/rank-vendors",
        json=[{"name": "Vendor", "score": 101, "reasoning": "Invalid"}],
    )
    assert response.status_code == 400


def test_rejects_fake_pdf_before_parsing():
    response = client.post(
        "/score-vendor",
        files={"file": ("proposal.pdf", b"not-a-pdf", "application/pdf")},
        data={"rfp_criteria": "Provide 24/7 support."},
    )
    assert response.status_code == 400
    assert "valid PDF" in response.json()["detail"]
