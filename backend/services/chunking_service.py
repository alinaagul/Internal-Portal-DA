"""
chunking_service.py — Semantic + Structure-Aware Chunking for Contracts
========================================================================
PURPOSE:
  Second step in the pipeline. Takes the OCR full_text and splits it into
  meaningful, retrievable chunks that respect legal document structure.

WHY THIS FILE EXISTS:
  Generic fixed-size chunking (e.g. every 512 tokens) is catastrophic for
  contracts. It would cut "payment shall be made within 30 days" across two
  chunks, destroying the meaning. This service:
    1. Detects contract sections (Article I, Section 2.3, ANNEX A, etc.)
    2. Splits on semantic boundaries FIRST (clause ends, paragraphs)
    3. Falls back to sentence-level splitting only for oversized paragraphs
    4. Preserves tables as atomic single chunks (never split a table)
    5. Adds 15% token overlap so cross-clause references are never lost
    6. Stores BM25-ready raw_content (undecorated text) separate from
       context-enriched content (prefixed with section title for embeddings)

OUTPUT:
  list[TextChunk] — each chunk carries:
    content       : str   — text fed to embedding model (has section prefix)
    raw_content   : str   — plain text used for BM25 keyword index
    chunk_index   : int
    page_start/end: int
    section_title : str   — e.g. "ARTICLE IX – TERMINATION"
    chunk_type    : str   — "text" | "table" | "header"
    token_count   : int

OLLAMA MODEL: Not used here — chunking is deterministic.

BM25 NOTE:
  The `raw_content` field (no section prefix noise) should be indexed with
  rank_bm25 in embedding_service.py for hybrid retrieval.
"""

import re
import logging
from typing import List, Tuple, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ─── Data class ───────────────────────────────────────────────────────────────

@dataclass
class TextChunk:
    content: str            # enriched text (section prefix + body) → for embedding
    raw_content: str        # plain body text → for BM25 index
    chunk_index: int
    page_start: int
    page_end: int
    section_title: Optional[str]
    chunk_type: str         # "text" | "table" | "header"
    token_count: int


# ─── Service ──────────────────────────────────────────────────────────────────

class ChunkingService:
    """
    Section-aware hierarchical chunker.
    Call: chunking_service.chunk(full_text, pages) → list[TextChunk]
    """

    # Legal document section header patterns (case-insensitive, multiline)
    SECTION_PATTERNS = [
        r"^(ARTICLE\s+[IVXLCDM\d]+[\.\s].{0,80})$",
        r"^(SECTION\s+\d+[\.\d]*.{0,80})$",
        r"^(SCHEDULE\s+[IVXLCDM\d]+[\.\s].{0,80})$",
        r"^(ANNEX\s+[IVXLCDM\d]+[\.\s].{0,80})$",
        r"^(EXHIBIT\s+[IVXLCDM\d]+[\.\s].{0,80})$",
        r"^(\d+\.\d+\s+[A-Z][A-Za-z\s]{3,60})$",   # numbered subsection
        r"^([A-Z][A-Z\s]{5,60})$",                   # ALL CAPS heading
    ]

    def __init__(
        self,
        chunk_size: int = 600,      # target tokens per chunk (~2400 chars)
        chunk_overlap: int = 90,    # ~15% overlap for cross-reference continuity
        min_chunk_size: int = 50,   # discard fragments smaller than this
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self._section_re = re.compile(
            "|".join(self.SECTION_PATTERNS),
            re.MULTILINE | re.IGNORECASE,
        )

    def chunk(self, full_text: str, pages: list = None) -> List[TextChunk]:
        """
        Main entry point.
        pages: list[PageResult] — optional, used for page number assignment.
        """
        if not full_text.strip():
            logger.warning("[Chunker] Empty text — nothing to chunk")
            return []

        logger.info("[Chunker] Starting section-aware chunking…")

        # ── Step 1: Split on section headers ──────────────────────────────────
        sections = self._split_into_sections(full_text)
        logger.info(f"[Chunker] Detected {len(sections)} sections")

        chunks: List[TextChunk] = []
        chunk_index = 0

        # ── Step 2: Process each section ──────────────────────────────────────
        for section_title, section_text in sections:
            # Tables → single atomic chunks (never split)
            table_chunks, remaining = self._extract_tables(
                section_text, section_title, chunk_index
            )
            chunks.extend(table_chunks)
            chunk_index += len(table_chunks)

            # Regular text → paragraph/sentence-aware chunks
            text_chunks = self._chunk_text(remaining, section_title, chunk_index)
            chunks.extend(text_chunks)
            chunk_index += len(text_chunks)

        # ── Step 3: Assign page numbers ───────────────────────────────────────
        if pages:
            chunks = self._assign_pages(chunks, pages)
        else:
            for c in chunks:
                c.page_start = 1
                c.page_end = 1

        # ── Step 4: Filter micro-fragments ────────────────────────────────────
        chunks = [c for c in chunks if len(c.raw_content.strip()) >= self.min_chunk_size]

        # Re-index after filtering
        for i, c in enumerate(chunks):
            c.chunk_index = i

        logger.info(f"[Chunker] Final chunk count: {len(chunks)}")
        return chunks

    # ── Section splitting ─────────────────────────────────────────────────────

    def _split_into_sections(self, text: str) -> List[Tuple[Optional[str], str]]:
        sections = []
        matches = list(self._section_re.finditer(text))

        if not matches:
            return [(None, text)]   # No headers → whole doc is one section

        # Preamble before first header
        if matches[0].start() > 0:
            preamble = text[: matches[0].start()].strip()
            if preamble:
                sections.append((None, preamble))

        for i, match in enumerate(matches):
            title = match.group(0).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            if body:
                sections.append((title, body))

        return sections

    # ── Table extraction ──────────────────────────────────────────────────────

    def _extract_tables(
        self, text: str, section_title: Optional[str], start_index: int
    ) -> Tuple[List[TextChunk], str]:
        """
        Pull [TABLE]...[/TABLE] blocks as atomic chunks.
        Returns (table_chunks, remaining_text_without_tables).
        """
        table_re = re.compile(r"\[TABLE\](.*?)\[/TABLE\]", re.DOTALL)
        tables: List[TextChunk] = []
        idx = start_index

        for m in table_re.finditer(text):
            body = m.group(1).strip()
            if not body:
                continue
            prefix = f"[Table — {section_title or 'document'}]\n"
            tables.append(TextChunk(
                content=prefix + body,
                raw_content=body,
                chunk_index=idx,
                page_start=1,
                page_end=1,
                section_title=section_title,
                chunk_type="table",
                token_count=self._count_tokens(body),
            ))
            idx += 1

        remaining = table_re.sub("", text).strip()
        return tables, remaining

    # ── Text chunking ─────────────────────────────────────────────────────────

    def _chunk_text(
        self, text: str, section_title: Optional[str], start_index: int
    ) -> List[TextChunk]:
        """
        Split text respecting paragraph → sentence hierarchy.
        Each chunk gets the section title prepended to its `content`
        (helps embedding model understand context) but NOT to `raw_content`
        (keeps BM25 from matching section names as keywords).
        """
        if not text.strip():
            return []

        paragraphs = [p.strip() for p in re.split(r"\n\n+", text) if p.strip()]
        chunks: List[TextChunk] = []
        current_paras: List[str] = []
        current_tokens = 0
        idx = start_index

        for para in paragraphs:
            para_tokens = self._count_tokens(para)

            # Oversized paragraph → sentence-level split
            if para_tokens > self.chunk_size:
                if current_paras:
                    body = "\n\n".join(current_paras)
                    chunks.append(self._make_chunk(body, section_title, idx))
                    idx += 1
                    overlap = self._get_overlap(body)
                    current_paras = [overlap] if overlap else []
                    current_tokens = self._count_tokens(overlap)

                sent_chunks = self._split_by_sentences(para, section_title, idx)
                chunks.extend(sent_chunks)
                idx += len(sent_chunks)
                continue

            # Flush buffer when it would overflow
            if current_tokens + para_tokens > self.chunk_size and current_paras:
                body = "\n\n".join(current_paras)
                chunks.append(self._make_chunk(body, section_title, idx))
                idx += 1
                overlap = self._get_overlap(body)
                current_paras = [overlap] if overlap else []
                current_tokens = self._count_tokens(overlap)

            current_paras.append(para)
            current_tokens += para_tokens

        # Flush remainder
        if current_paras:
            body = "\n\n".join(current_paras)
            chunks.append(self._make_chunk(body, section_title, idx))

        return chunks

    def _split_by_sentences(
        self, text: str, section_title: Optional[str], start_index: int
    ) -> List[TextChunk]:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks: List[TextChunk] = []
        current: List[str] = []
        current_tokens = 0
        idx = start_index

        for sent in sentences:
            st = self._count_tokens(sent)
            if current_tokens + st > self.chunk_size and current:
                body = " ".join(current)
                chunks.append(self._make_chunk(body, section_title, idx))
                idx += 1
                overlap = current[-2:] if len(current) >= 2 else current[-1:]
                current = list(overlap)
                current_tokens = sum(self._count_tokens(s) for s in current)
            current.append(sent)
            current_tokens += st

        if current:
            chunks.append(self._make_chunk(" ".join(current), section_title, idx))

        return chunks

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _make_chunk(
        self, body: str, section_title: Optional[str], index: int
    ) -> TextChunk:
        """
        Build a TextChunk.
        content     = section prefix + body   (fed to Ollama embedding)
        raw_content = body only               (fed to BM25 index)
        """
        content = f"[{section_title}]\n{body}" if section_title else body
        return TextChunk(
            content=content,
            raw_content=body,
            chunk_index=index,
            page_start=1,
            page_end=1,
            section_title=section_title,
            chunk_type="text",
            token_count=self._count_tokens(content),
        )

    def _get_overlap(self, text: str) -> str:
        words = text.split()
        return " ".join(words[-self.chunk_overlap:]) if len(words) > self.chunk_overlap else text

    def _count_tokens(self, text: str) -> int:
        """Approximation: 1 token ≈ 4 chars for English legal text."""
        return max(1, len(text) // 4)

    def _assign_pages(self, chunks: List[TextChunk], pages: list) -> List[TextChunk]:
        total_pages = len(pages)
        total_chunks = len(chunks)
        if total_chunks == 0:
            return chunks
        for i, chunk in enumerate(chunks):
            pi = int(i / total_chunks * total_pages)
            chunk.page_start = pages[pi].page_number
            chunk.page_end = pages[min(pi + 1, total_pages - 1)].page_number
        return chunks


# Singleton
chunking_service = ChunkingService()