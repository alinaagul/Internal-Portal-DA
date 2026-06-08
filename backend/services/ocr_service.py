"""
ocr_service.py — Multi-Strategy OCR for Contract PDFs
======================================================
PURPOSE:
  First step in the pipeline. Extracts text (+ tables) from uploaded PDFs/images.
  Two strategies:
    1. pdfplumber  — fast, perfect for digitally-created PDFs (text layer exists)
    2. PyMuPDF + pytesseract — fallback for scanned PDFs (image-only, no text layer)
       PyMuPDF renders pages to images entirely in Python (no poppler / no system
       dependencies). pytesseract then reads the images.
       Install: pip install pymupdf pytesseract
       Tesseract binary: https://github.com/UB-Mannheim/tesseract/wiki

WHY THIS FILE EXISTS:
  Contracts arrive as PDFs. Many are scanned (no embedded text).
  Without OCR you'd get empty strings → no embeddings → no retrieval.
  OCR confidence is tracked per page and stored so the API response can
  surface "low confidence — please verify original" warnings.

OUTPUT:
  OCRResult dataclass containing:
    - pages          : list[PageResult]  (per-page text + tables + confidence)
    - full_text      : str               (concatenated cleaned text)
    - avg_confidence : float             (0–100; used in API response)
    - total_pages    : int
    - language       : str               ("en" | "ar" | "unknown")
    - has_tables     : bool
    - extraction_method : str            ("pdfplumber" | "tesseract" | "combined")

OLLAMA MODEL: Not used here — OCR is deterministic (no LLM involved).
"""

import re
import logging
from pathlib import Path
from typing import List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class PageResult:
    page_number: int
    raw_text: str
    structured_text: str
    confidence: float          # 0–100
    has_tables: bool
    tables: List[List[List[str]]] = field(default_factory=list)
    extraction_method: str = "pdfplumber"


@dataclass
class OCRResult:
    pages: List[PageResult]
    full_text: str
    avg_confidence: float
    total_pages: int
    language: str
    has_tables: bool
    extraction_method: str
    # Per-page stats for API response
    pages_with_low_confidence: int = 0   # pages < 60% confidence
    pages_with_tables: int = 0


# ─── Service ──────────────────────────────────────────────────────────────────

class OCRService:
    """
    Multi-strategy OCR.
    Call: ocr_service.extract(file_path) → OCRResult
    """

    MIN_TEXT_PER_PAGE = 50      # chars; below → page is likely a scanned image
    LOW_CONFIDENCE_THRESHOLD = 60.0

    def extract(self, file_path: str) -> OCRResult:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        logger.info(f"[OCR] Extracting: {path.name}")

        # Always try pdfplumber first (fast, zero-cost for text PDFs)
        pages = self._extract_with_pdfplumber(file_path)

        # Decide if we need to fallback to Tesseract
        empty_pages = sum(
            1 for p in pages
            if len(p.structured_text.strip()) < self.MIN_TEXT_PER_PAGE
        )

        if pages and empty_pages > len(pages) * 0.5:
            logger.info(
                f"[OCR] {empty_pages}/{len(pages)} pages near-empty → trying Tesseract"
            )
            tesseract_pages = self._extract_with_tesseract(file_path)
            if tesseract_pages:
                pages  = tesseract_pages
                method = "tesseract"
            else:
                # Tesseract unavailable (missing poppler / pytesseract) — keep
                # pdfplumber output even if sparse rather than failing entirely.
                logger.warning(
                    "[OCR] Tesseract fallback produced no pages — keeping pdfplumber output.\n"
                    "  To enable scanned PDF support, install the Tesseract binary:\n"
                    "    1. Download installer: https://github.com/UB-Mannheim/tesseract/wiki\n"
                    "    2. During install, check 'Add to PATH'\n"
                    "    3. Restart the server\n"
                    "  (PyMuPDF is already installed — no poppler needed)"
                )
                method = "pdfplumber"
        else:
            method = "pdfplumber"

        if not pages:
            raise RuntimeError(
                "OCR produced no pages — check file format.\n"
                "If this is a scanned PDF, ensure poppler is installed and in PATH.\n"
                "Download: https://github.com/oschwartz10612/poppler-windows/releases"
            )

        # Aggregate stats
        avg_conf = sum(p.confidence for p in pages) / len(pages)
        full_text = "\n\n".join(p.structured_text for p in pages if p.structured_text.strip())
        has_tables = any(p.has_tables for p in pages)
        low_conf_pages = sum(1 for p in pages if p.confidence < self.LOW_CONFIDENCE_THRESHOLD)
        table_pages = sum(1 for p in pages if p.has_tables)
        language = self._detect_language(full_text[:2000])

        logger.info(
            f"[OCR] Done — {len(pages)} pages | avg_conf={avg_conf:.1f}% | "
            f"tables_on={table_pages} pages | method={method}"
        )

        return OCRResult(
            pages=pages,
            full_text=full_text,
            avg_confidence=round(avg_conf, 2),
            total_pages=len(pages),
            language=language,
            has_tables=has_tables,
            extraction_method=method,
            pages_with_low_confidence=low_conf_pages,
            pages_with_tables=table_pages,
        )

    # ── Strategy 1: pdfplumber ────────────────────────────────────────────────

    def _extract_with_pdfplumber(self, file_path: str) -> List[PageResult]:
        try:
            import pdfplumber
        except ImportError:
            logger.warning("[OCR] pdfplumber not installed — pip install pdfplumber")
            return []

        pages = []
        try:
            with pdfplumber.open(file_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    raw_text = page.extract_text() or ""

                    # Extract tables
                    tables = []
                    for tbl in (page.extract_tables() or []):
                        if tbl:
                            tables.append([[cell or "" for cell in row] for row in tbl])

                    structured = self._clean_text(raw_text)

                    # Append tables as [TABLE]...[/TABLE] markers for chunker
                    for tbl in tables:
                        structured += f"\n[TABLE]\n{self._table_to_text(tbl)}\n[/TABLE]\n"

                    # Confidence heuristic: text density relative to page area
                    area = max(1.0, (page.width or 600) * (page.height or 800))
                    confidence = min(100.0, len(raw_text.strip()) / area * 50_000)
                    confidence = max(0.0, confidence)

                    pages.append(PageResult(
                        page_number=i + 1,
                        raw_text=raw_text,
                        structured_text=structured,
                        confidence=round(confidence, 2),
                        has_tables=len(tables) > 0,
                        tables=tables,
                        extraction_method="pdfplumber",
                    ))
        except Exception as e:
            logger.error(f"[OCR] pdfplumber error: {e}")

        return pages

    # ── Strategy 2: PyMuPDF + Tesseract (scanned PDFs) ───────────────────────
    # PyMuPDF (fitz) renders PDF pages to images entirely in Python —
    # no poppler, no system dependencies, no PATH configuration needed.
    # Install: pip install pymupdf pytesseract
    # (Tesseract binary still required: https://github.com/UB-Mannheim/tesseract/wiki)

    def _extract_with_tesseract(self, file_path: str) -> List[PageResult]:
        try:
            import pytesseract
        except ImportError:
            logger.warning(
                "[OCR] pytesseract not installed — pip install pytesseract\n"
                "      Also install Tesseract binary: "
                "https://github.com/UB-Mannheim/tesseract/wiki"
            )
            return []

        # Point pytesseract at the Tesseract binary explicitly.
        # This works even if Tesseract is not on the system PATH.
        # Windows default install path is used as fallback.
        import os, shutil
        if not shutil.which("tesseract"):
            # Check env variable first, then Windows default install path
            env_path = os.environ.get("TESSERACT_CMD", "")
            windows_default = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            tesseract_path  = env_path if env_path and os.path.isfile(env_path) \
                              else windows_default if os.path.isfile(windows_default) \
                              else None
            if tesseract_path:
                pytesseract.pytesseract.tesseract_cmd = tesseract_path
                logger.info(f"[OCR] Tesseract not in PATH — using: {tesseract_path}")
            else:
                logger.warning(
                    "[OCR] Tesseract binary not found in PATH or default location.\n"
                    "      Set the path explicitly by adding this to your .env or config:\n"
                    "        TESSERACT_CMD=C:\\path\\to\\tesseract.exe\n"
                    "      Or add Tesseract to your system PATH and restart."
                )

        # Ensure tessdata language files are locatable.
        # Tesseract needs TESSDATA_PREFIX to point to the folder containing eng.traineddata.
        if not os.environ.get("TESSDATA_PREFIX"):
            windows_tessdata = r"C:\Program Files\Tesseract-OCR\tessdata"
            if os.path.isdir(windows_tessdata):
                os.environ["TESSDATA_PREFIX"] = windows_tessdata
                logger.info(f"[OCR] TESSDATA_PREFIX not set — using: {windows_tessdata}")

        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.warning(
                "[OCR] PyMuPDF not installed — pip install pymupdf\n"
                "      PyMuPDF replaces pdf2image/poppler with zero system dependencies."
            )
            return []

        pages = []
        try:
            doc = fitz.open(file_path)
            for i, page in enumerate(doc):
                # Render at 300 DPI — matrix scale = 300/72 ≈ 4.17
                mat  = fitz.Matrix(300 / 72, 300 / 72)
                pix  = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)

                # Convert PyMuPDF pixmap → PIL Image (no disk I/O needed)
                from PIL import Image
                import io
                img = Image.open(io.BytesIO(pix.tobytes("png")))

                # Tesseract OCR
                data = pytesseract.image_to_data(
                    img,
                    output_type=pytesseract.Output.DICT,
                    config="--psm 6",   # Assume uniform block of text
                )
                confidences = [int(c) for c in data["conf"] if str(c).lstrip("-").isdigit() and int(c) > 0]
                avg_conf    = sum(confidences) / len(confidences) if confidences else 0.0

                raw_text   = pytesseract.image_to_string(img, config="--psm 6")
                structured = self._clean_text(raw_text)

                pages.append(PageResult(
                    page_number      = i + 1,
                    raw_text         = raw_text,
                    structured_text  = structured,
                    confidence       = round(avg_conf, 2),
                    has_tables       = False,
                    extraction_method= "tesseract+pymupdf",
                ))

            doc.close()

        except Exception as e:
            logger.error(f"[OCR] Tesseract+PyMuPDF error: {e}")

        return pages

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _clean_text(self, text: str) -> str:
        """Remove scanning artifacts, normalize whitespace, merge broken lines."""
        if not text:
            return ""

        # Strip control characters (keep \n and \t)
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

        # Remove scanning artifacts (repeated symbols)
        text = re.sub(r"[|]{3,}", " ", text)
        text = re.sub(r"-{5,}", " ", text)
        text = re.sub(r"_{5,}", " ", text)
        text = re.sub(r"\.{4,}", "...", text)

        # Fix hyphenated line breaks: "termi-\nnation" → "termination"
        text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)

        # Normalize whitespace per line
        lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]

        # Merge continuation lines (short lines not ending in punctuation)
        merged, i = [], 0
        while i < len(lines):
            ln = lines[i]
            while (
                i + 1 < len(lines)
                and ln
                and len(ln) < 80
                and ln[-1] not in ".!?:;)"
                and lines[i + 1]
                and not lines[i + 1][0].isupper()
            ):
                i += 1
                ln += " " + lines[i]
            merged.append(ln)
            i += 1

        text = "\n".join(merged)
        text = re.sub(r"\n{3,}", "\n\n", text)   # Max 2 consecutive blank lines
        return text.strip()

    def _table_to_text(self, table: List[List[str]]) -> str:
        rows = []
        for row in table:
            cells = [str(c).strip() for c in row if c]
            if cells:
                rows.append(" | ".join(cells))
        return "\n".join(rows)

    def _detect_language(self, text: str) -> str:
        if not text.strip():
            return "unknown"
        arabic = sum(1 for c in text if "\u0600" <= c <= "\u06ff")
        return "ar" if arabic > len(text) * 0.1 else "en"


# Singleton — import this everywhere
ocr_service = OCRService()