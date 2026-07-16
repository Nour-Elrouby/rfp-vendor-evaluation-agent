"""Centralized, validated application configuration."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _positive_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer.") from exc
    if value < minimum:
        raise RuntimeError(f"{name} must be at least {minimum}.")
    return value


def _boolean(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be true or false.")


def _hosts() -> tuple[str, ...]:
    hosts = tuple(
        host.strip()
        for host in os.getenv("ALLOWED_HOSTS", "*").split(",")
        if host.strip()
    )
    if not hosts:
        raise RuntimeError("ALLOWED_HOSTS must contain at least one host.")
    return hosts


@dataclass(frozen=True)
class Settings:
    app_env: str
    api_auth_token: str | None
    allowed_hosts: tuple[str, ...]
    enable_docs: bool
    max_request_bytes: int
    max_upload_bytes: int
    max_criteria_chars: int
    max_extracted_chars: int
    max_chat_rfp_chars: int
    max_question_chars: int
    max_rank_vendors: int
    max_audit_page_size: int
    rate_limit_per_minute: int
    max_concurrent_evaluations: int

    @property
    def production(self) -> bool:
        return self.app_env == "production"


def load_settings() -> Settings:
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    if app_env not in {"development", "test", "production"}:
        raise RuntimeError("APP_ENV must be development, test, or production.")

    token = os.getenv("API_AUTH_TOKEN", "").strip() or None
    hosts = _hosts()
    if app_env == "production":
        if not token or len(token) < 32:
            raise RuntimeError(
                "Production requires API_AUTH_TOKEN with at least 32 characters."
            )
        if not os.getenv("GROQ_API_KEY", "").strip():
            raise RuntimeError("Production requires GROQ_API_KEY for the RFP assistant.")
        if "*" in hosts:
            raise RuntimeError(
                "Production requires explicit ALLOWED_HOSTS; wildcard is not allowed."
            )

    max_upload = _positive_int("MAX_UPLOAD_BYTES", 15 * 1024 * 1024)
    return Settings(
        app_env=app_env,
        api_auth_token=token,
        allowed_hosts=hosts,
        enable_docs=_boolean("ENABLE_DOCS", app_env != "production"),
        max_request_bytes=_positive_int(
            "MAX_REQUEST_BYTES", max_upload + 1_000_000
        ),
        max_upload_bytes=max_upload,
        max_criteria_chars=_positive_int("MAX_CRITERIA_CHARS", 20_000),
        max_extracted_chars=_positive_int("MAX_EXTRACTED_CHARS", 1_000_000),
        max_chat_rfp_chars=_positive_int("MAX_CHAT_RFP_CHARS", 200_000),
        max_question_chars=_positive_int("MAX_QUESTION_CHARS", 2_000),
        max_rank_vendors=_positive_int("MAX_RANK_VENDORS", 500),
        max_audit_page_size=_positive_int("MAX_AUDIT_PAGE_SIZE", 200),
        rate_limit_per_minute=_positive_int("RATE_LIMIT_PER_MINUTE", 60),
        max_concurrent_evaluations=_positive_int(
            "MAX_CONCURRENT_EVALUATIONS", 2
        ),
    )


settings = load_settings()
