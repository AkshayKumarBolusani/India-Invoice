"""FastAPI boundary for the existing India Invoice AI workflows."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from invoice_ai.workflow import compare_file, process_batch, process_file
from invoice_ai.ingestion import DocumentIngestionError


MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))
MAX_BATCH_FILES = int(os.getenv("MAX_BATCH_FILES", "20"))
SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tiff", ".bmp", ".txt"}


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "india-invoice-ai-api"
    llm_configured: bool
    llm_model: str | None
    max_upload_bytes: int


class ProcessingResponse(BaseModel):
    filename: str
    status: str
    invoice: dict[str, Any] | None
    validation: dict[str, Any] | None
    metadata: dict[str, Any]
    error: str | None = None


class BatchResponse(BaseModel):
    results: list[ProcessingResponse]
    total: int
    completed: int
    failed: int


class CompareResponse(BaseModel):
    filename: str
    rules: dict[str, Any]
    rules_validation: dict[str, Any]
    llm: dict[str, Any]
    llm_validation: dict[str, Any]
    llm_metadata: dict[str, Any]
    comparison: dict[str, Any]


class EvaluationResponse(BaseModel):
    available: bool
    reports: dict[str, Any] = Field(default_factory=dict)
    note: str


app = FastAPI(title="India Invoice AI API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080,http://127.0.0.1:8080",
    ).split(","),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(DocumentIngestionError)
async def document_ingestion_error_handler(_, exc: DocumentIngestionError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


def _public_result(result: dict[str, Any]) -> dict[str, Any]:
    """Remove source markdown from network responses unless a future explicit route opts in."""
    return {key: value for key, value in result.items() if key != "source_markdown"}


async def _save_upload(upload: UploadFile, directory: Path) -> Path:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"Unsupported document format: {suffix or 'none'}")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"upload{suffix}"
    size = 0
    with target.open("wb") as handle:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="Uploaded document exceeds the configured size limit.")
            handle.write(chunk)
    return target


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        llm_configured=bool(os.getenv("LLM_MODEL")),
        llm_model=os.getenv("LLM_MODEL") or None,
        max_upload_bytes=MAX_UPLOAD_BYTES,
    )


@app.post("/api/process", response_model=ProcessingResponse)
async def process_document(file: UploadFile = File(...), engine: str = "rules-based") -> ProcessingResponse:
    with tempfile.TemporaryDirectory(prefix="invoice-ai-") as directory:
        path = await _save_upload(file, Path(directory))
        result = await asyncio.to_thread(process_file, path, engine)
    result["filename"] = file.filename or result["filename"]
    return ProcessingResponse.model_validate(_public_result(result))


@app.post("/api/batch", response_model=BatchResponse)
async def process_documents(files: list[UploadFile] = File(...), engine: str = "rules-based") -> BatchResponse:
    if not files or len(files) > MAX_BATCH_FILES:
        raise HTTPException(status_code=400, detail=f"Batch size must be between 1 and {MAX_BATCH_FILES} files.")
    with tempfile.TemporaryDirectory(prefix="invoice-ai-batch-") as directory:
        root = Path(directory)
        prepared = []
        failures = {}
        for index, upload in enumerate(files):
            try:
                prepared.append((index, upload, await _save_upload(upload, root / str(index))))
            except HTTPException as exc:
                failures[index] = {
                    "filename": upload.filename or f"file-{index}",
                    "status": "processing_failed",
                    "invoice": None,
                    "validation": None,
                    "metadata": {},
                    "error": str(exc.detail),
                }
        processed = await asyncio.to_thread(
            process_batch, [path for _, _, path in prepared], engine
        )
        for (index, upload, _), result in zip(prepared, processed):
            result["filename"] = upload.filename or result["filename"]
            failures[index] = result
        results = [failures[index] for index in range(len(files))]
    public_results = [ProcessingResponse.model_validate(_public_result(result)) for result in results]
    return BatchResponse(
        results=public_results,
        total=len(public_results),
        completed=sum(result.status != "processing_failed" for result in public_results),
        failed=sum(result.status == "processing_failed" for result in public_results),
    )


@app.post("/api/compare", response_model=CompareResponse)
async def compare_document(file: UploadFile = File(...)) -> CompareResponse:
    with tempfile.TemporaryDirectory(prefix="invoice-ai-compare-") as directory:
        path = await _save_upload(file, Path(directory))
        result = await asyncio.to_thread(compare_file, path)
    return CompareResponse.model_validate(_public_result(result))


@app.get("/api/evaluation", response_model=EvaluationResponse)
async def evaluation() -> EvaluationResponse:
    root = Path(__file__).resolve().parent
    report_paths = {
        "dataset_audit": root / "evaluation" / "dataset_audit_summary.json",
        "batch": root / "evaluation" / "batch_report.json",
        "baseline": root / "evaluation" / "baseline_report.json",
    }
    reports = {}
    for name, path in report_paths.items():
        if path.exists():
            import json

            reports[name] = json.loads(path.read_text(encoding="utf-8"))
    return EvaluationResponse(
        available=bool(reports),
        reports=reports,
        note="Stored metrics are traceable reports; synthetic fixtures and public parser outputs are not production ground truth.",
    )