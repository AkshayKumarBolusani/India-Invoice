"""Document ingestion with explicit image/OCR validation."""

from __future__ import annotations

import importlib.util
import os
import shutil
import time
from functools import lru_cache
from pathlib import Path

from docling.document_converter import DocumentConverter


SUPPORTED_IMAGE_FORMATS = {".png", ".jpg", ".jpeg", ".webp", ".tiff", ".bmp"}
SUPPORTED_DOCLING_FORMATS = {".pdf", *SUPPORTED_IMAGE_FORMATS}
DEFAULT_MAX_FILE_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))
DEFAULT_MAX_IMAGE_PIXELS = int(os.getenv("MAX_IMAGE_PIXELS", "50000000"))


class DocumentIngestionError(ValueError):
    """Actionable error raised when a document cannot be safely read."""


def _ocr_backend() -> str | None:
    """Return an installed OCR backend that Docling can use, without starting it."""
    if importlib.util.find_spec("rapidocr"):
        return "rapidocr"
    if importlib.util.find_spec("docling_ocr"):
        return "docling_ocr"
    if importlib.util.find_spec("pytesseract") and shutil.which("tesseract"):
        return "tesseract"
    return None


def _validate_image(path: Path) -> tuple[int, int]:
    try:
        from PIL import Image, UnidentifiedImageError

        with Image.open(path) as image:
            width, height = image.size
            if width <= 0 or height <= 0:
                raise DocumentIngestionError("Image has no readable pixels.")
            if width * height > DEFAULT_MAX_IMAGE_PIXELS:
                raise DocumentIngestionError(
                    f"Image dimensions exceed the safety limit of {DEFAULT_MAX_IMAGE_PIXELS:,} pixels."
                )
            image.verify()
            return width, height
    except DocumentIngestionError:
        raise
    except (UnidentifiedImageError, OSError) as exc:
        raise DocumentIngestionError(
            "The uploaded image is corrupt or its content does not match its file type."
        ) from exc


@lru_cache(maxsize=1)
def get_document_converter() -> DocumentConverter:
    """Reuse one converter instead of initializing it for every document."""
    return DocumentConverter()


def extract_document(
    file_path: str,
    max_file_size: int = DEFAULT_MAX_FILE_BYTES,
) -> dict:
    """Extract normalized Markdown from text, PDF, or Docling-supported image input."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Document not found: {path}")
    if path.stat().st_size > max_file_size:
        raise DocumentIngestionError(
            f"Document exceeds the configured size limit of {max_file_size:,} bytes."
        )

    suffix = path.suffix.lower()
    if suffix == ".txt":
        started = time.perf_counter()
        markdown = path.read_text(encoding="utf-8")
        timings = {"text_read_seconds": round(time.perf_counter() - started, 4)}
        method = "direct_text"
        ocr_backend = None
    elif suffix in SUPPORTED_DOCLING_FORMATS:
        if suffix in SUPPORTED_IMAGE_FORMATS:
            width, height = _validate_image(path)
            ocr_backend = _ocr_backend()
            if ocr_backend is None:
                raise DocumentIngestionError(
                    "No supported OCR runtime is installed for image invoices. "
                    "Install the project dependencies with .venv/bin/pip install -r requirements.txt."
                )
        else:
            width = height = None
            ocr_backend = None

        started = time.perf_counter()
        converter = get_document_converter()
        result = converter.convert(str(path), max_file_size=max_file_size)
        conversion_seconds = time.perf_counter() - started
        markdown = result.document.export_to_markdown()
        timings = {
            "conversion_seconds": round(conversion_seconds, 4),
        }
        if suffix in SUPPORTED_IMAGE_FORMATS:
            timings["ocr_seconds"] = round(conversion_seconds, 4)
            timings["image_width"] = width
            timings["image_height"] = height
        method = "docling_image_ocr" if suffix in SUPPORTED_IMAGE_FORMATS else "docling"
    else:
        raise ValueError(f"Unsupported document format: {suffix}")

    if not markdown or not markdown.strip():
        if suffix in SUPPORTED_IMAGE_FORMATS:
            raise DocumentIngestionError(
                "OCR returned no readable text. Try a sharper, better-lit, upright image "
                "or verify that the document contains legible text."
            )
        raise DocumentIngestionError("Document conversion returned no readable text.")

    return {
        "filename": path.name,
        "markdown": markdown,
        "text_length": len(markdown),
        "method": method,
        "ocr_backend": ocr_backend,
        "timings": timings,
    }
