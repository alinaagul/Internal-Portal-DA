import re
import io
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PageResult:
    page_number: int
    raw_text: str
    structured_text: str
    confidence: float
    has_tables: bool
    tables: List[List[List[str]]] = field(default_factory=list)
    extraction_method: str = "pdfplumber"  # pdfplumber / tesseract / combined


@dataclass
class OCRResult:
    pages: List[PageResult]
    full_text: str
    avg_confidence: float
    total_pages: int
    language: str
    has_tables: bool
    extraction_method: str


class OCRService:
    """
    Multi-strategy OCR service for contract PDFs.
    Strategy:
      1. Try pdfplumber (fast, for text-layer PDFs)
      2. If confidence low → fallback to pytesseract (for scanned PDFs)
      3. Detect and preserve tables
      4. Clean artifacts from scanning
    """

    MIN_CONFIDENCE_THRESHOLD = 40.0   # below this → use tesseract
    MIN_TEXT_PER_PAGE = 50            # chars; below this page is likely scanned

    def extract(self, file_path: str) -> OCRResult:
        """Main entry point — auto-detects best extraction strategy."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        logger.info(f"[OCR] Starting extraction: {path.name}")

        # Try pdfplumber first (handles text-layer PDFs perfectly)
        pages = self._extract_with_pdfplumber(file_path)

        # Check if pdfplumber got enough text
        avg_conf = sum(p.confidence for p in pages) / len(pages) if pages else 0
        low_text_pages = sum(1 for p in pages if len(p.structured_text.strip()) < self.MIN_TEXT_PER_PAGE)

        if low_text_pages > len(pages) * 0.5:
            # More than 50% pages are empty → scanned PDF → use tesseract
            logger.info(f"[OCR] Low text detected ({low_text_pages}/{len(pages)} pages) → using Tesseract")
            pages = self._extract_with_tesseract(file_path)
            method = "tesseract"
        else:
            method = "pdfplumber"

        # Re-calculate stats
        avg_conf = sum(p.confidence for p in pages) / len(pages) if pages else 0
        full_text = "\n\n".join(p.structured_text for p in pages if p.structured_text.strip())
        has_tables = any(p.has_tables for p in pages)
        language = self._detect_language(full_text[:2000])

        logger.info(f"[OCR] Done — {len(pages)} pages, avg confidence: {avg_conf:.1f}%, method: {method}")

        return OCRResult(
            pages=pages,
            full_text=full_text,
            avg_confidence=avg_conf,
            total_pages=len(pages),
            language=language,
            has_tables=has_tables,
            extraction_method=method,
        )

    def _extract_with_pdfplumber(self, file_path: str) -> List[PageResult]:
        """Extract text using pdfplumber — best for text-layer PDFs."""
        try:
            import pdfplumber
        except ImportError:
            logger.warning("[OCR] pdfplumber not installed, skipping")
            return []

        pages = []
        try:
            with pdfplumber.open(file_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    raw_text = page.extract_text() or ""
                    
                    # Extract tables
                    tables = []
                    table_data = page.extract_tables() or []
                    for tbl in table_data:
                        if tbl:
                            tables.append([[cell or "" for cell in row] for row in tbl])

                    structured = self._clean_text(raw_text)
                    
                    # Add table content as text
                    for tbl in tables:
                        table_text = self._table_to_text(tbl)
                        structured += f"\n[TABLE]\n{table_text}\n[/TABLE]\n"

                    # Confidence estimate: based on text density
                    confidence = min(100.0, len(raw_text.strip()) / max(1, page.width * page.height) * 50000)
                    confidence = max(0.0, min(100.0, confidence))

                    pages.append(PageResult(
                        page_number=i + 1,
                        raw_text=raw_text,
                        structured_text=structured,
                        confidence=confidence,
                        has_tables=len(tables) > 0,
                        tables=tables,
                        extraction_method="pdfplumber",
                    ))
        except Exception as e:
            logger.error(f"[OCR] pdfplumber failed: {e}")

        return pages

    def _extract_with_tesseract(self, file_path: str) -> List[PageResult]:
        """Fallback OCR using pytesseract for scanned PDFs."""
        try:
            import pytesseract
            from pdf2image import convert_from_path
            from PIL import Image
        except ImportError:
            logger.warning("[OCR] pytesseract/pdf2image not installed — using pdfplumber only")
            return self._extract_with_pdfplumber(file_path)

        pages = []
        try:
            images = convert_from_path(file_path, dpi=300)
            for i, image in enumerate(images):
                # Preprocess: convert to grayscale for better OCR
                gray = image.convert("L")

                # Run tesseract with confidence data
                data = pytesseract.image_to_data(
                    gray,
                    output_type=pytesseract.Output.DICT,
                    config="--psm 6",  # assume uniform block of text
                )

                # Calculate average confidence (ignore -1 values)
                confidences = [int(c) for c in data["conf"] if int(c) > 0]
                avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

                raw_text = pytesseract.image_to_string(gray, config="--psm 6")
                structured = self._clean_text(raw_text)

                pages.append(PageResult(
                    page_number=i + 1,
                    raw_text=raw_text,
                    structured_text=structured,
                    confidence=avg_conf,
                    has_tables=False,
                    extraction_method="tesseract",
                ))
        except Exception as e:
            logger.error(f"[OCR] Tesseract failed: {e}")

        return pages

    def _clean_text(self, text: str) -> str:
        """Clean OCR artifacts and normalize text for contract documents."""
        if not text:
            return ""

        # Remove null bytes and control chars (keep newlines and tabs)
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

        # Remove repeated special chars (scanning artifacts like ||||, -----)
        text = re.sub(r"[|]{3,}", " ", text)
        text = re.sub(r"[-]{5,}", " ", text)
        text = re.sub(r"[_]{5,}", " ", text)
        text = re.sub(r"[.]{4,}", "...", text)

        # Fix broken hyphenated words (word- \n word → word word)
        text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)

        # Normalize whitespace within lines
        lines = text.split("\n")
        cleaned_lines = []
        for line in lines:
            line = re.sub(r"[ \t]+", " ", line).strip()
            cleaned_lines.append(line)

        # Merge lines that are clearly continuation (no sentence end)
        merged = []
        i = 0
        while i < len(cleaned_lines):
            line = cleaned_lines[i]
            # Merge short lines that don't end with punctuation
            while (i + 1 < len(cleaned_lines) and
                   line and
                   len(line) < 80 and
                   not line[-1] in ".!?:;)" and
                   cleaned_lines[i + 1] and
                   not cleaned_lines[i + 1][0].isupper()):
                i += 1
                line = line + " " + cleaned_lines[i]
            merged.append(line)
            i += 1

        # Remove empty lines clusters (max 2 consecutive empty lines)
        text = "\n".join(merged)
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    def _table_to_text(self, table: List[List[str]]) -> str:
        """Convert extracted table to readable text format."""
        rows = []
        for row in table:
            cells = [str(cell).strip() for cell in row if cell]
            if cells:
                rows.append(" | ".join(cells))
        return "\n".join(rows)

    def _detect_language(self, text: str) -> str:
        """Simple language detection — extend with langdetect if needed."""
        if not text.strip():
            return "unknown"
        # Simple heuristic: check for Arabic/Urdu chars
        arabic_chars = sum(1 for c in text if "\u0600" <= c <= "\u06ff")
        if arabic_chars > len(text) * 0.1:
            return "ar"
        return "en"


# Singleton
ocr_service = OCRService()