import os
import subprocess
import sys


def _run(code: str, **environment: str):
    env = os.environ.copy()
    env.update(environment)
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_production_rejects_missing_auth_token():
    result = _run(
        "import config",
        APP_ENV="production",
        API_AUTH_TOKEN="",
        ALLOWED_HOSTS="procurelens.example.com",
        GROQ_API_KEY="test-only",
    )
    assert result.returncode != 0
    assert "API_AUTH_TOKEN" in result.stderr


def test_production_authentication_is_enforced():
    token = "a" * 48
    code = """
from fastapi.testclient import TestClient
from main import app
client = TestClient(app)
payload = [{"name": "Vendor", "score": 80, "reasoning": "Fit"}]
assert client.post("/rank-vendors", json=payload).status_code == 401
assert client.post(
    "/rank-vendors", json=payload, headers={"X-API-Key": "a" * 48}
).status_code == 200
assert app.docs_url is None
"""
    result = _run(
        code,
        APP_ENV="production",
        API_AUTH_TOKEN=token,
        ALLOWED_HOSTS="testserver",
        GROQ_API_KEY="test-only",
    )
    assert result.returncode == 0, result.stderr
