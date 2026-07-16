import json
import os
from pathlib import Path
from typing import Any

from groq import APIConnectionError, APIStatusError, APITimeoutError, Groq
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")
MODEL_NAME = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


class GroqError(RuntimeError):
    """Raised when Groq cannot complete a valid JSON generation request."""


def generate_json(prompt: str, model: str | None = None) -> dict[str, Any]:
    """Send a prompt to Groq and return the generated JSON object."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string.")
    if model is not None and (not isinstance(model, str) or not model.strip()):
        raise ValueError("model must be a non-empty string when provided.")

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise GroqError(
            "GROQ_API_KEY is not set. Add it to .env or the server environment."
        )

    selected_model = model.strip() if model is not None else MODEL_NAME
    client = Groq(api_key=api_key, timeout=120.0)

    try:
        completion = client.chat.completions.create(
            model=selected_model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_completion_tokens=512,
            temperature=0,
        )
    except APITimeoutError as exc:
        raise GroqError("Groq did not respond within 120 seconds.") from exc
    except APIConnectionError as exc:
        raise GroqError("Could not connect to the Groq API.") from exc
    except APIStatusError as exc:
        detail = str(exc)
        if len(detail) > 300:
            detail = detail[:300] + "..."
        raise GroqError(f"Groq returned HTTP status {exc.status_code}: {detail}") from exc
    except Exception as exc:
        raise GroqError(f"Groq request failed: {exc}") from exc

    if not completion.choices:
        raise GroqError("Groq returned no response choices.")

    content = completion.choices[0].message.content
    if not isinstance(content, str) or not content.strip():
        raise GroqError("Groq response did not contain the expected text field.")

    try:
        result = json.loads(content)
    except json.JSONDecodeError as exc:
        raise GroqError("Groq generated invalid JSON.") from exc

    if not isinstance(result, dict):
        raise GroqError("Groq generated JSON that was not an object.")
    return result
