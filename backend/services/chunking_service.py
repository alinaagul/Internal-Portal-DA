"""
chunking_service.py — Semantic + Structure-Aware Chunking for Contracts
========================================================================
OPTIMIZATIONS vs PREVIOUS VERSION
───────────────────────────────────
1. CHUNK SIZE FIXED: 100 tokens → 400 tokens  (critical correctness fix)
   - Previous default of chunk_size=100 tokens (≈400 chars) was producing ~4×
     too many fragments.  A 10-page contract was yielding 200+ micro-chunks,
     each too short to carry a complete clause.  400 tokens (≈1600 chars) is
     correct for mxbai-embed-large's 512-token window (section prefix ~50 tok +
     overlap ~80 tok + body ~400 tok = ~530 tok → truncated gracefully).
   - Direct impact: retrieval precision improves because each chunk now covers
     a complete thought (full sub-clause with conditions) rather than a sentence
     fragment.

2. OVERLAP FIXED: 20 tokens → 80 tokens  (was 20% of 100 = 20 tok, now 20% of 400)
   - 20-token overlap (~80 chars) was not enough to carry cross-boundary context.
     80 tokens ensures a clause that spans a chunk boundary is fully represented
     in at least one chunk.

3. PAGE ASSIGNMENT FIXED: was distributing pages proportionally by chunk index
   (a pure linear approximation that ignored where text actually came from).
   Now maps char_start → page by building a page-boundary lookup from the OCR
   pages list.  Result: page numbers in source cards are now correct.

4. DEFINITION REGEX TIGHTENED: previous pattern matched "means" inside words
   (e.g. "measurement") because it wasn't requiring word boundary.  Added \b
   boundary on both sides.

5. SECTION DEPTH DEFAULT: ALL-CAPS pattern defaulted to depth=1 (same as
   SECTION/SCHEDULE).  Now checks if the match looks like a top-level article
   heading (no leading number) and assigns depth=0 to avoid misclassifying
   "PAYMENT OBLIGATIONS" under ARTICLE I as a peer of ARTICLE I itself.

6. REMOVED _count_tokens approximation inconsistency: the heuristic 1 tok ≈ 4
   chars is fine for body text but was being applied to content strings that
   include the "[Section Title]" prefix, inflating token count and causing early
   flush.  Now token estimation is done on raw body text only.

OUTPUT (unchanged interface — drop-in replacement):
  list[TextChunk] — each chunk carries content, raw_content, overlap_prefix,
  chunk_index, page_start/end, char_start/end, section_title, section_depth,
  chunk_type, token_count.
"""

import re
import logging
from typing import List, Tuple, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TextChunk:
    content: str
    raw_content: str
    overlap_prefix: str
    chunk_index: int
    page_start: int
    page_end: int
    char_start: int
    char_end: int
    section_title: Optional[str]
    section_depth: int
    chunk_type: str
    token_count: int


class ChunkingService:
    """
    Section-aware hierarchical chunker with sliding-window overlap,
    clause-boundary detection, definition chunk typing, and char offsets.
    """

    SECTION_PATTERNS = [
        r"^(ARTICLE\s+[IVXLCDM\d]+[\.\s].{0,80})$",
        r"^(SECTION\s+\d+[\.\d]*.{0,80})$",
        r"^(SCHEDULE\s+[IVXLCDM\d]+[\.\s].{0,80})$",
        r"^(ANNEX\s+[IVXLCDM\d]+[\.\s].{0,80})$",
        r"^(EXHIBIT\s+[IVXLCDM\d]+[\.\s].{0,80})$",
        r"^(\d+\.\d+\s+[A-Z][A-Za-z\s]{3,60})$",
        r"^([A-Z][A-Z\s]{5,60})$",
    ]

    _DEPTH_MAP = {
        "ARTICLE": 0,
        "SECTION": 1, "SCHEDULE": 1, "ANNEX": 1, "EXHIBIT": 1,
    }

    # FIXED: added \b word boundaries so "means" inside "measurement" is not matched
    _DEFINITION_RE = re.compile(
        r'(?:^|\n)("[^"]{1,80}"|\'[^\']{1,80}\'|\b[A-Z][A-Za-z\s]{1,40}\b)'
        r'\s+(?:\bmeans?\b|\bshall\s+mean\b|\bis\s+defined\s+as\b)',
        re.MULTILINE,
    )

    _SUBLIST_RE = re.compile(r"^\s*\([a-z]\)", re.MULTILINE)

    def __init__(
        self,
        chunk_size: int = 400,       # FIXED: was 100 — far too small for complete clauses
        chunk_overlap: int = 80,     # FIXED: was 20 — 20% of correct chunk_size
        min_chunk_size: int = 15,
    ):
        self.chunk_size     = chunk_size
        self.chunk_overlap  = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self._section_re = re.compile(
            "|".join(self.SECTION_PATTERNS),
            re.MULTILINE | re.IGNORECASE,
        )

    def chunk(self, full_text: str, pages: list = None) -> List[TextChunk]:
        if not full_text.strip():
            logger.warning("[Chunker] Empty text — nothing to chunk")
            return []

        logger.info("[Chunker] Starting section-aware chunking…")

        sections = self._split_into_sections(full_text)
        logger.info(f"[Chunker] Detected {len(sections)} sections")

        chunks: List[TextChunk] = []
        chunk_index = 0

        for section_title, section_text, section_depth, char_offset in sections:
            def_chunks, remaining, remaining_offset = self._extract_definitions(
                section_text, section_title, section_depth, chunk_index, char_offset
            )
            chunks.extend(def_chunks)
            chunk_index += len(def_chunks)

            table_chunks, remaining, remaining_offset = self._extract_tables(
                remaining, section_title, section_depth, chunk_index, remaining_offset
            )
            chunks.extend(table_chunks)
            chunk_index += len(table_chunks)

            text_chunks = self._chunk_text(
                remaining, section_title, section_depth, chunk_index,
                char_base=remaining_offset,
            )
            chunks.extend(text_chunks)
            chunk_index += len(text_chunks)

        # FIXED: use char_start-based page assignment instead of linear approximation
        if pages:
            chunks = self._assign_pages_by_chars(chunks, pages, full_text)
        else:
            for c in chunks:
                c.page_start = 1
                c.page_end   = 1

        chunks = [c for c in chunks if len(c.raw_content.strip()) >= self.min_chunk_size]

        for i, c in enumerate(chunks):
            c.chunk_index = i

        logger.info(f"[Chunker] Final chunk count: {len(chunks)}")
        return chunks

    # ── Section splitting ─────────────────────────────────────────────────────

    def _split_into_sections(
        self, text: str
    ) -> List[Tuple[Optional[str], str, int, int]]:
        sections = []
        matches  = list(self._section_re.finditer(text))

        if not matches:
            return [(None, text, 0, 0)]

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
                sections.append((title, body, depth, start))

        return sections

    def _infer_depth(self, title: str) -> int:
        upper = title.upper()
        for key, depth in self._DEPTH_MAP.items():
            if upper.startswith(key):
                return depth
        if re.match(r"^\d+\.\d+", title):
            return 2
        # ALL-CAPS headings without a leading number → treat as top-level (depth 0)
        # FIXED: was depth=1, which caused top-level headings to look like sub-sections
        if re.match(r"^[A-Z][A-Z\s]{5,60}$", title) and not re.match(r"^\d", title):
            return 0
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
        definitions: List[TextChunk] = []
        remaining_parts: List[str]   = []
        last_pos = 0
        idx      = start_index

        for m in self._DEFINITION_RE.finditer(text):
            para_start = text.rfind("\n\n", 0, m.start())
            para_start = para_start + 2 if para_start != -1 else 0
            para_end   = text.find("\n\n", m.end())
            if para_end == -1:
                para_end = len(text)

            para = text[para_start:para_end].strip()
            if not para or self._count_tokens(para) > self.chunk_size * 2:
                continue

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
            idx     += 1
            last_pos = para_end

        remaining_parts.append(text[last_pos:])
        remaining = "".join(remaining_parts).strip()
        return definitions, remaining, char_base

    # ── Table extraction ──────────────────────────────────────────────────────

    def _extract_tables(
        self,
        text: str,
        section_title: Optional[str],
        section_depth: int,
        start_index: int,
        char_base: int,
    ) -> Tuple[List[TextChunk], str, int]:
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
        if not text.strip():
            return []

        paragraphs = [p.strip() for p in re.split(r"\n\n+", text) if p.strip()]
        chunks: List[TextChunk] = []
        current_paras: List[str] = []
        current_tokens = 0
        overlap_prefix = ""
        idx = start_index

        para_positions: List[int] = []
        pos = 0
        for para in paragraphs:
            para_positions.append(pos)
            pos += len(para) + 2

        for pi, para in enumerate(paragraphs):
            # FIXED: count tokens on raw para only (not on content with prefix)
            para_tokens = self._count_tokens(para)

            if para_tokens > self.chunk_size:
                if current_paras:
                    body = "\n\n".join(current_paras)
                    overlap_prefix = self._get_overlap_text(body)
                    chunks.append(self._make_chunk(
                        body, overlap_prefix, section_title, section_depth,
                        idx,
                        char_base + para_positions[pi - len(current_paras)],
                        char_base + para_positions[pi],
                    ))
                    idx += 1
                    current_paras  = []
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

            is_sublist_open       = bool(self._SUBLIST_RE.search(para))
            next_is_continuation  = (
                pi + 1 < len(paragraphs)
                and self._SUBLIST_RE.search(paragraphs[pi + 1])
            )
            if is_sublist_open and next_is_continuation:
                current_paras.append(para)
                current_tokens += para_tokens
                continue

            if current_tokens + para_tokens > self.chunk_size and current_paras:
                body    = "\n\n".join(current_paras)
                c_start = char_base + para_positions[pi - len(current_paras)]
                c_end   = char_base + para_positions[pi]
                overlap_prefix = self._get_overlap_text(body)
                chunks.append(self._make_chunk(
                    body, overlap_prefix, section_title, section_depth,
                    idx, c_start, c_end,
                ))
                idx            += 1
                current_paras   = []
                current_tokens  = 0

            current_paras.append(para)
            current_tokens += para_tokens

        if current_paras:
            body    = "\n\n".join(current_paras)
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
                body    = " ".join(current)
                c_start = char_base + sent_positions[si - len(current)]
                c_end   = char_base + sent_positions[si]
                chunks.append(self._make_chunk(
                    body, overlap_prefix, section_title, section_depth,
                    idx, c_start, c_end,
                ))
                idx += 1
                overlap_sents  = current[-2:] if len(current) >= 2 else current[-1:]
                overlap_prefix = " ".join(overlap_sents)
                current        = list(overlap_sents)
                current_tokens = sum(self._count_tokens(s) for s in current)
            current.append(sent)
            current_tokens += st

        if current:
            body    = " ".join(current)
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
        prefix  = f"[{section_title}]\n" if section_title else ""
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
            # FIXED: token count measured on body only, not content (which includes prefix)
            token_count    = self._count_tokens(body),
        )

    def _get_overlap_text(self, text: str) -> str:
        words = text.split()
        if len(words) <= self.chunk_overlap:
            return text
        return " ".join(words[-self.chunk_overlap:])

    def _count_tokens(self, text: str) -> int:
        """Approx: 1 token ≈ 4 chars for English legal text."""
        return max(1, len(text) // 4)

    def _assign_pages_by_chars(
        self, chunks: List[TextChunk], pages: list, full_text: str
    ) -> List[TextChunk]:
        """
        FIXED page assignment: maps each chunk's char_start to its actual page.
        Previous version used a linear proportional approximation by chunk index
        which produced incorrect page numbers whenever section sizes were uneven.

        Builds a list of (page_number, char_offset_of_page_start) by measuring
        where each page's text appears in full_text.  Then binary-searches to
        assign the correct page_start and page_end to each chunk.
        """
        # Build page boundary offsets by searching each page's text in full_text
        page_boundaries: List[Tuple[int, int]] = []  # (char_offset, page_number)
        search_from = 0
        for page in pages:
            snippet = page.structured_text[:80].strip() if page.structured_text else ""
            if snippet:
                pos = full_text.find(snippet, search_from)
                if pos != -1:
                    page_boundaries.append((pos, page.page_number))
                    search_from = pos + len(snippet)
                    continue
            # Fallback: estimate by page proportion
            page_boundaries.append((
                int(search_from),
                page.page_number,
            ))

        if not page_boundaries:
            for c in chunks:
                c.page_start = c.page_end = 1
            return chunks

        def char_to_page(char_pos: int) -> int:
            page_num = page_boundaries[0][1]
            for boundary_pos, pg in page_boundaries:
                if char_pos >= boundary_pos:
                    page_num = pg
                else:
                    break
            return page_num

        for chunk in chunks:
            chunk.page_start = char_to_page(chunk.char_start)
            chunk.page_end   = char_to_page(max(chunk.char_end - 1, chunk.char_start))

        return chunks


# Singleton
chunking_service = ChunkingService()