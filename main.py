import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from audit import audit_vendor_score, get_audit_trail
from chatbot import answer_question
from groq_client import GroqError
from ranking import rank_vendors
from reader import SUPPORTED_EXTENSIONS, extract_vendor_text
from scoring import score_vendor

app = FastAPI()


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


@app.post("/score-vendor")
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
    if not isinstance(rfp_criteria, str) or not rfp_criteria.strip():
        raise HTTPException(status_code=400, detail="RFP criteria cannot be empty.")

    contents = await file.read()
    await file.close()
    if not contents:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

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
            raise HTTPException(
                status_code=400,
                detail="The proposal file is corrupt or could not be read.",
            ) from exc

        try:
            score_result = await run_in_threadpool(score_vendor, text, rfp_criteria)
            audit_record = await run_in_threadpool(
                audit_vendor_score,
                filename,
                text,
                rfp_criteria,
                score_result,
            )
        except GroqError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass

    return audit_record


@app.post("/rank-vendors")
async def rank_vendors_endpoint(vendor_scores: list[dict[str, Any]]):
    try:
        return rank_vendors(vendor_scores)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/chat")
async def chat_endpoint(question: str = Form(...), rfp_text: str = Form(...)):
    try:
        answer = await run_in_threadpool(answer_question, question, rfp_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except GroqError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"answer": answer}


# Retrieve the audit trail for all vendors, or filter it to one vendor.
@app.get("/audit-trail")
async def audit_trail_endpoint(vendor_name: str | None = None):
    try:
        return await run_in_threadpool(get_audit_trail, vendor_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
