import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from audit import audit_vendor_score, get_audit_trail
from chatbot import answer_question
from config import BASE_DIR, settings
from embedding_client import EmbeddingError, get_model
from groq_client import GroqError
from ranking import rank_vendors
from reader import SUPPORTED_EXTENSIONS, extract_vendor_text, validate_file_signature
from scoring import score_vendor
from security import (
    RateLimitMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
    require_api_key,
)

logger = logging.getLogger("procurelens")
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

docs_url = "/docs" if settings.enable_docs else None
openapi_url = "/openapi.json" if settings.enable_docs else None
app = FastAPI(
    title="ProcureLens API",
    description="Embedding-based vendor scoring with a Groq-powered RFP assistant.",
    version="1.1.0",
    docs_url=docs_url,
    redoc_url=None,
    openapi_url=openapi_url,
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=list(settings.allowed_hosts),
)
app.add_middleware(
    RateLimitMiddleware,
    requests_per_minute=settings.rate_limit_per_minute,
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    RequestSizeLimitMiddleware,
    max_bytes=settings.max_request_bytes,
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

_evaluation_slots = asyncio.Semaphore(settings.max_concurrent_evaluations)
_protected = [Depends(require_api_key)]


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled request failure on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected server error occurred."},
    )


@app.get("/", include_in_schema=False)
async def root():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(BASE_DIR / "static" / "favicon.svg")


@app.get("/health/live", include_in_schema=False)
async def health_live():
    return {"status": "ok"}


@app.get("/health/ready", include_in_schema=False)
async def health_ready():
    return {
        "status": "ready",
        "environment": settings.app_env,
        "embedding_model_loaded": get_model.cache_info().currsize > 0,
        "chat_configured": bool(os.getenv("GROQ_API_KEY")),
        "authentication_enabled": settings.api_auth_token is not None,
    }


async def _read_upload(file: UploadFile) -> bytes:
    contents = bytearray()
    try:
        while chunk := await file.read(1024 * 1024):
            contents.extend(chunk)
            if len(contents) > settings.max_upload_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=(
                        "Uploaded file exceeds the "
                        f"{settings.max_upload_bytes // (1024 * 1024)} MB limit."
                    ),
                )
    finally:
        await file.close()
    return bytes(contents)


@app.post("/score-vendor", dependencies=_protected)
async def score_vendor_endpoint(file: UploadFile, rfp_criteria: str = Form(...)):
    filename = Path(file.filename or "").name
    extension = Path(filename).suffix.lower()
    if not filename:
        raise HTTPException(status_code=400, detail="The upload must have a filename.")
    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Use one of: {supported}.",
        )

    criteria = rfp_criteria.strip()
    if not criteria:
        raise HTTPException(status_code=400, detail="RFP criteria cannot be empty.")
    if len(criteria) > settings.max_criteria_chars:
        raise HTTPException(status_code=413, detail="RFP criteria are too long.")

    contents = await _read_upload(file)
    if not contents:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    try:
        validate_file_signature(contents, extension)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as temporary:
            temporary.write(contents)
            temporary_path = temporary.name

        try:
            text = await run_in_threadpool(extract_vendor_text, temporary_path)
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid proposal: {exc}") from exc
        except Exception as exc:
            logger.warning("Proposal extraction failed for %s: %s", filename, exc)
            raise HTTPException(
                status_code=400,
                detail="The proposal file is corrupt or could not be read.",
            ) from exc

        if len(text) > settings.max_extracted_chars:
            raise HTTPException(
                status_code=413,
                detail="The extracted proposal text exceeds the processing limit.",
            )

        try:
            async with _evaluation_slots:
                score_result = await run_in_threadpool(score_vendor, text, criteria)
                audit_record = await run_in_threadpool(
                    audit_vendor_score,
                    filename,
                    text,
                    criteria,
                    score_result,
                )
        except EmbeddingError as exc:
            logger.error("Embedding service failure: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="The local scoring model is temporarily unavailable.",
            ) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass

    return audit_record


@app.post("/rank-vendors", dependencies=_protected)
async def rank_vendors_endpoint(vendor_scores: list[dict[str, Any]]):
    if len(vendor_scores) > settings.max_rank_vendors:
        raise HTTPException(status_code=413, detail="Too many vendors to rank.")
    try:
        return rank_vendors(vendor_scores)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/chat", dependencies=_protected)
async def chat_endpoint(question: str = Form(...), rfp_text: str = Form(...)):
    question = question.strip()
    rfp_text = rfp_text.strip()
    if not question or not rfp_text:
        raise HTTPException(
            status_code=400,
            detail="question and rfp_text must be non-empty.",
        )
    if len(question) > settings.max_question_chars:
        raise HTTPException(status_code=413, detail="The question is too long.")
    if len(rfp_text) > settings.max_chat_rfp_chars:
        raise HTTPException(status_code=413, detail="The supplied RFP text is too long.")

    try:
        answer = await run_in_threadpool(answer_question, question, rfp_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EmbeddingError as exc:
        logger.error("Chat retrieval failure: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="The local retrieval model is temporarily unavailable.",
        ) from exc
    except GroqError as exc:
        logger.error("Groq assistant failure: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="The RFP assistant is temporarily unavailable.",
        ) from exc
    return {"answer": answer}


@app.get("/audit-trail", dependencies=_protected)
async def audit_trail_endpoint(
    vendor_name: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
):
    limit = min(limit, settings.max_audit_page_size)
    try:
        return await run_in_threadpool(
            get_audit_trail,
            vendor_name,
            offset=offset,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.error("Audit trail read failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="The audit trail could not be read.",
        ) from exc
