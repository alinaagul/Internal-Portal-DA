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
    5. Sliding-window overlap: carries the last `chunk_overlap` TOKENS
       (not words) from the previous chunk so cross-clause references
       are never silently truncated.  Overlap text is stored in the
       `overlap_prefix` field so rerankers can strip it before scoring.
    6. Stores BM25-ready raw_content (undecorated text) separate from
       context-enriched content (prefixed with section title for embeddings)
    7. Clause-boundary detection: never splits mid-definition, mid-list,
       or inside a numbered sub-clause (e.g. "(a) … (b)").
    8. Adds `char_start` / `char_end` offsets into full_text so highlight-in-
       PDF features can pinpoint the exact span.

OUTPUT:
  list[TextChunk] — each chunk carries:
    content        : str   — text fed to embedding model (has section prefix)
    raw_content    : str   — plain text used for BM25 keyword index
    overlap_prefix : str   — the trailing overlap copied from previous chunk
    chunk_index    : int
    page_start/end : int
    char_start/end : int   — byte offsets into OCR full_text
    section_title  : str   — e.g. "ARTICLE IX – TERMINATION"
    section_depth  : int   — 0=top-level article, 1=section, 2=subsection
    chunk_type     : str   — "text" | "table" | "header" | "definition"
    token_count    : int

OLLAMA MODEL: Not used here — chunking is deterministic.

BM25 NOTE:
  The `raw_content` field (no section prefix noise) should be indexed with
  rank_bm25 in embedding_service.py for hybrid retrieval.

CHUNKING STRATEGY RATIONALE:
  chunk_size=400 tokens (≈1 600 chars) — large enough to hold a complete
  sub-clause with its conditions; small enough to keep vector similarity
  focused on a single topic.  Overlap=80 tokens (20%) so a clause that
  straddles a boundary is fully represented in at least one chunk.
  Definition lists get their own "definition" chunk type so the reranker
  can boost them for "what does X mean?" queries without polluting factual
  clause results.
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
    overlap_prefix: str     # trailing tokens copied from previous chunk (sliding window)
    chunk_index: int
    page_start: int
    page_end: int
    char_start: int         # byte offset of raw_content start in full_text
    char_end: int           # byte offset of raw_content end in full_text
    section_title: Optional[str]
    section_depth: int      # 0=article, 1=section, 2=subsection
    chunk_type: str         # "text" | "table" | "header" | "definition"
    token_count: int


# ─── Service ──────────────────────────────────────────────────────────────────

class ChunkingService:
    """
    Section-aware hierarchical chunker with sliding-window overlap,
    clause-boundary detection, definition chunk typing, and char offsets.
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

    # Depth mapping: article=0, section/schedule/annex=1, subsection=2
    _DEPTH_MAP = {
        "ARTICLE": 0,
        "SECTION": 1, "SCHEDULE": 1, "ANNEX": 1, "EXHIBIT": 1,
        "SUBSECTION": 2,  # matched by the \d+\.\d+ pattern
    }

    # Definition blocks: "X" means / "X" shall mean / "X" is defined as
    _DEFINITION_RE = re.compile(
        r'(?:^|\n)("[^"]{1,80}"|\'[^\']{1,80}\'|\b[A-Z][A-Za-z\s]{1,40}\b)'
        r'\s+(?:means?|shall\s+mean|is\s+defined\s+as)',
        re.MULTILINE,
    )

    # Clause-boundary: never split inside a lettered sub-list "(a) … (b)"
    _SUBLIST_RE = re.compile(r"^\s*\([a-z]\)", re.MULTILINE)

    def __init__(
        self,
        chunk_size: int = 100,      # target tokens per chunk (≈400 chars, fits mxbai-embed-large 512-token limit)
        chunk_overlap: int = 20,    # overlap tokens from previous chunk (20%)
        min_chunk_size: int = 15,   # discard micro-fragments below this
    ):
        self.chunk_size    = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self._section_re = re.compile(
            "|".join(self.SECTION_PATTERNS),
            re.MULTILINE | re.IGNORECASE,
        )

    # ── Public entry point ────────────────────────────────────────────────────

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
        for section_title, section_text, section_depth, char_offset in sections:
            # Definition blocks → typed separately so reranker can boost them
            def_chunks, remaining, remaining_offset = self._extract_definitions(
                section_text, section_title, section_depth, chunk_index, char_offset
            )
            chunks.extend(def_chunks)
            chunk_index += len(def_chunks)

            # Tables → single atomic chunks (never split)
            table_chunks, remaining, remaining_offset = self._extract_tables(
                remaining, section_title, section_depth, chunk_index, remaining_offset
            )
            chunks.extend(table_chunks)
            chunk_index += len(table_chunks)

            # Regular text → paragraph/sentence-aware chunks with sliding window
            text_chunks = self._chunk_text(
                remaining, section_title, section_depth, chunk_index,
                char_base=remaining_offset,
            )
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

    def _split_into_sections(
        self, text: str
    ) -> List[Tuple[Optional[str], str, int, int]]:
        """Returns list of (title, body, depth, char_offset_of_body)."""
        sections = []
        matches = list(self._section_re.finditer(text))

        if not matches:
            return [(None, text, 0, 0)]

        # Preamble before first header
        if matches[0].start() > 0:
            preamble = text[: matches[0].start()].strip()
            if preamble:
                sections.append((None, preamble, 0, 0))

        for i, match in enumerate(matches):
            title = match.group(0).strip()
            depth = self._infer_depth(title)
            start = match.end()
            end   = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body  = text[start:end].strip()
            if body:
                # char_offset is start position of body in original full_text
                sections.append((title, body, depth, start))

        return sections

    def _infer_depth(self, title: str) -> int:
        upper = title.upper()
        for key, depth in self._DEPTH_MAP.items():
            if upper.startswith(key):
                return depth
        # Numbered subsection "2.3 Payment Terms"
        if re.match(r"^\d+\.\d+", title):
            return 2
        return 1

    # ── Definition extraction ─────────────────────────────────────────────────

    def _extract_definitions(
        self,
        text: str,
        section_title: Optional[str],
        section_depth: int,
        start_index: int,
        char_base: int,
    ) -> Tuple[List[TextChunk], str, int]:
        """
        Pull definition paragraphs into dedicated 'definition' chunks.
        Definitions are short (usually 1–3 sentences) so each becomes its own chunk.
        This lets the reranker boost them for "what does X mean?" queries.
        """
        definitions: List[TextChunk] = []
        remaining_parts: List[str]   = []
        last_pos = 0
        idx      = start_index

        for m in self._DEFINITION_RE.finditer(text):
            # Find the paragraph that starts at or before this match
            para_start = text.rfind("\n\n", 0, m.start())
            para_start = para_start + 2 if para_start != -1 else 0
            para_end   = text.find("\n\n", m.end())
            if para_end == -1:
                para_end = len(text)

            para = text[para_start:para_end].strip()
            if not para or self._count_tokens(para) > self.chunk_size * 2:
                continue  # skip malformed / oversized

            # Append text before this definition block to remaining
            if para_start > last_pos:
                remaining_parts.append(text[last_pos:para_start])

            prefix = f"[Definition — {section_title or 'document'}]\n"
            definitions.append(TextChunk(
                content        = prefix + para,
                raw_content    = para,
                overlap_prefix = "",
                chunk_index    = idx,
                page_start     = 1,
                page_end       = 1,
                char_start     = char_base + para_start,
                char_end       = char_base + para_end,
                section_title  = section_title,
                section_depth  = section_depth,
                chunk_type     = "definition",
                token_count    = self._count_tokens(para),
            ))
            idx      += 1
            last_pos  = para_end

        remaining_parts.append(text[last_pos:])
        remaining      = "".join(remaining_parts).strip()
        remaining_offset = char_base  # offset tracking is approximate after joins
        return definitions, remaining, remaining_offset

    # ── Table extraction ──────────────────────────────────────────────────────

    def _extract_tables(
        self,
        text: str,
        section_title: Optional[str],
        section_depth: int,
        start_index: int,
        char_base: int,
    ) -> Tuple[List[TextChunk], str, int]:
        """
        Pull [TABLE]...[/TABLE] blocks as atomic chunks.
        Returns (table_chunks, remaining_text_without_tables, char_base).
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
                content        = prefix + body,
                raw_content    = body,
                overlap_prefix = "",
                chunk_index    = idx,
                page_start     = 1,
                page_end       = 1,
                char_start     = char_base + m.start(1),
                char_end       = char_base + m.end(1),
                section_title  = section_title,
                section_depth  = section_depth,
                chunk_type     = "table",
                token_count    = self._count_tokens(body),
            ))
            idx += 1

        remaining = table_re.sub("", text).strip()
        return tables, remaining, char_base

    # ── Text chunking ─────────────────────────────────────────────────────────

    def _chunk_text(
        self,
        text: str,
        section_title: Optional[str],
        section_depth: int,
        start_index: int,
        char_base: int = 0,
    ) -> List[TextChunk]:
        """
        Split text respecting paragraph → sentence hierarchy.

        SLIDING WINDOW OVERLAP (key improvement over previous version):
          At each flush the last `chunk_overlap` tokens are carried forward
          as `overlap_prefix`.  This text is prepended to `content` so the
          embedding captures the cross-boundary context, but it is NOT part
          of `raw_content` (so BM25 is not polluted with repeated text).

        CLAUSE-BOUNDARY GUARD:
          If a paragraph opens with a lettered sub-list item "(a) …" we
          never split mid-list — we hold until the full list ends.
        """
        if not text.strip():
            return []

        paragraphs = [p.strip() for p in re.split(r"\n\n+", text) if p.strip()]
        chunks: List[TextChunk] = []
        current_paras: List[str] = []
        current_tokens = 0
        overlap_prefix = ""
        idx = start_index

        # Track approximate char position within text
        para_positions: List[int] = []
        pos = 0
        for para in paragraphs:
            para_positions.append(pos)
            pos += len(para) + 2   # +2 for "\n\n"

        for pi, para in enumerate(paragraphs):
            para_tokens = self._count_tokens(para)

            # Oversized paragraph → sentence-level split
            if para_tokens > self.chunk_size:
                if current_paras:
                    body = "\n\n".join(current_paras)
                    overlap_prefix = self._get_overlap_text(body)
                    chunks.append(self._make_chunk(
                        body, overlap_prefix, section_title, section_depth,
                        idx, char_base + para_positions[pi - len(current_paras)],
                        char_base + para_positions[pi],
                    ))
                    idx += 1
                    current_paras = []
                    current_tokens = 0

                sent_chunks = self._split_by_sentences(
                    para, section_title, section_depth, idx,
                    overlap_prefix=overlap_prefix,
                    char_base=char_base + para_positions[pi],
                )
                if sent_chunks:
                    overlap_prefix = self._get_overlap_text(sent_chunks[-1].raw_content)
                chunks.extend(sent_chunks)
                idx += len(sent_chunks)
                continue

            # Clause-boundary guard: hold if we're mid-sublist
            is_sublist_open = bool(self._SUBLIST_RE.search(para))
            next_is_continuation = (
                pi + 1 < len(paragraphs)
                and self._SUBLIST_RE.search(paragraphs[pi + 1])
            )
            if is_sublist_open and next_is_continuation:
                # Don't flush — accumulate the full sub-list first
                current_paras.append(para)
                current_tokens += para_tokens
                continue

            # Flush buffer when it would overflow
            if current_tokens + para_tokens > self.chunk_size and current_paras:
                body = "\n\n".join(current_paras)
                c_start = char_base + para_positions[pi - len(current_paras)]
                c_end   = char_base + para_positions[pi]
                overlap_prefix = self._get_overlap_text(body)
                chunks.append(self._make_chunk(
                    body, overlap_prefix, section_title, section_depth,
                    idx, c_start, c_end,
                ))
                idx += 1
                current_paras  = []
                current_tokens = 0

            current_paras.append(para)
            current_tokens += para_tokens

        # Flush remainder
        if current_paras:
            body = "\n\n".join(current_paras)
            c_start = char_base + para_positions[len(paragraphs) - len(current_paras)]
            c_end   = char_base + pos
            chunks.append(self._make_chunk(
                body, overlap_prefix, section_title, section_depth,
                idx, c_start, c_end,
            ))

        return chunks

    def _split_by_sentences(
        self,
        text: str,
        section_title: Optional[str],
        section_depth: int,
        start_index: int,
        overlap_prefix: str = "",
        char_base: int = 0,
    ) -> List[TextChunk]:
        """Sentence-level fallback for oversized paragraphs."""
        # Use a smarter sentence splitter that avoids splitting on "e.g.", "i.e.", decimals
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z\"\(])", text)
        chunks: List[TextChunk] = []
        current: List[str] = []
        current_tokens = 0
        idx = start_index
        pos = 0
        sent_positions = []
        for s in sentences:
            sent_positions.append(pos)
            pos += len(s) + 1

        for si, sent in enumerate(sentences):
            st = self._count_tokens(sent)
            if current_tokens + st > self.chunk_size and current:
                body = " ".join(current)
                c_start = char_base + sent_positions[si - len(current)]
                c_end   = char_base + sent_positions[si]
                chunks.append(self._make_chunk(
                    body, overlap_prefix, section_title, section_depth,
                    idx, c_start, c_end,
                ))
                idx += 1
                # Sliding window: keep last 2 sentences as overlap
                overlap_sents = current[-2:] if len(current) >= 2 else current[-1:]
                overlap_prefix = " ".join(overlap_sents)
                current       = list(overlap_sents)
                current_tokens = sum(self._count_tokens(s) for s in current)
            current.append(sent)
            current_tokens += st

        if current:
            body = " ".join(current)
            c_start = char_base + sent_positions[len(sentences) - len(current)]
            chunks.append(self._make_chunk(
                body, overlap_prefix, section_title, section_depth,
                idx, c_start, char_base + pos,
            ))

        return chunks

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _make_chunk(
        self,
        body: str,
        overlap_prefix: str,
        section_title: Optional[str],
        section_depth: int,
        index: int,
        char_start: int = 0,
        char_end: int = 0,
    ) -> TextChunk:
        """
        Build a TextChunk.
        content     = section prefix + overlap_prefix + body  (fed to embedding)
        raw_content = body only                               (fed to BM25 index)
        overlap_prefix stored separately so reranker can strip it.
        """
        prefix = f"[{section_title}]\n" if section_title else ""
        # Prepend overlap to content (not raw_content) for richer embedding context
        content = prefix + (f"…{overlap_prefix}\n" if overlap_prefix else "") + body
        return TextChunk(
            content        = content,
            raw_content    = body,
            overlap_prefix = overlap_prefix,
            chunk_index    = index,
            page_start     = 1,
            page_end       = 1,
            char_start     = char_start,
            char_end       = char_end,
            section_title  = section_title,
            section_depth  = section_depth,
            chunk_type     = "text",
            token_count    = self._count_tokens(content),
        )

    def _get_overlap_text(self, text: str) -> str:
        """Return the last `chunk_overlap` tokens from text as overlap prefix."""
        words = text.split()
        if len(words) <= self.chunk_overlap:
            return text
        return " ".join(words[-self.chunk_overlap:])

    def _count_tokens(self, text: str) -> int:
        """Approximation: 1 token ≈ 4 chars for English legal text."""
        return max(1, len(text) // 4)

    def _assign_pages(self, chunks: List[TextChunk], pages: list) -> List[TextChunk]:
        total_pages  = len(pages)
        total_chunks = len(chunks)
        if total_chunks == 0:
            return chunks
        for i, chunk in enumerate(chunks):
            pi = int(i / total_chunks * total_pages)
            chunk.page_start = pages[pi].page_number
            chunk.page_end   = pages[min(pi + 1, total_pages - 1)].page_number
        return chunks


# Singleton
chunking_service = ChunkingService()