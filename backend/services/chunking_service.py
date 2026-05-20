import re
import logging
from typing import List, Tuple, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TextChunk:
    content: str
    chunk_index: int
    page_start: int
    page_end: int
    section_title: Optional[str]
    chunk_type: str          # text / table / header
    token_count: int
    raw_content: str = ""


class ChunkingService:
    """
    Section-aware chunking for legal/contract documents.
    
    Strategy:
    1. Split on article/section headers first (semantic boundaries)
    2. If section too large → split on paragraph boundaries
    3. If still too large → split on sentence boundaries with overlap
    4. Preserve tables as single chunks
    5. Add 15% overlap between chunks for context continuity
    """

    # Contract section patterns
    SECTION_PATTERNS = [
        r"^(ARTICLE\s+[IVXLCDM\d]+[\.\s].*?)$",
        r"^(SECTION\s+\d+[\.\d]*[\.\s].*?)$",
        r"^(SCHEDULE\s+[IVXLCDM\d]+[\.\s].*?)$",
        r"^(ANNEX\s+[IVXLCDM\d]+[\.\s].*?)$",
        r"^(EXHIBIT\s+[IVXLCDM\d]+[\.\s].*?)$",
        r"^(\d+\.\d*\s+[A-Z][A-Za-z\s]{3,50})$",
        r"^([A-Z][A-Z\s]{5,50})$",  # ALL CAPS headings
    ]

    def __init__(
        self,
        chunk_size: int = 600,       # target tokens per chunk
        chunk_overlap: int = 90,     # ~15% overlap
        min_chunk_size: int = 50,    # discard chunks smaller than this
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self._section_re = re.compile(
            "|".join(self.SECTION_PATTERNS), re.MULTILINE | re.IGNORECASE
        )

    def chunk(self, full_text: str, pages: list = None) -> List[TextChunk]:
        """
        Main chunking method.
        pages: list of PageResult objects (optional, for page tracking)
        """
        if not full_text.strip():
            return []

        logger.info("[Chunker] Starting section-aware chunking...")

        # Step 1: Split into sections
        sections = self._split_into_sections(full_text)
        logger.info(f"[Chunker] Found {len(sections)} sections")

        # Step 2: Process each section into chunks
        chunks: List[TextChunk] = []
        chunk_index = 0

        for section_title, section_text in sections:
            # Handle tables as single chunks
            table_chunks, remaining_text = self._extract_tables(section_text, section_title, chunk_index)
            chunks.extend(table_chunks)
            chunk_index += len(table_chunks)

            # Chunk remaining text
            text_chunks = self._chunk_text(remaining_text, section_title, chunk_index)
            chunks.extend(text_chunks)
            chunk_index += len(text_chunks)

        # Step 3: Assign page numbers (approximate)
        if pages:
            chunks = self._assign_pages(chunks, pages)
        else:
            for c in chunks:
                c.page_start = 1
                c.page_end = 1

        # Step 4: Filter tiny chunks
        chunks = [c for c in chunks if len(c.content.strip()) >= self.min_chunk_size]

        # Re-index after filtering
        for i, c in enumerate(chunks):
            c.chunk_index = i

        logger.info(f"[Chunker] Produced {len(chunks)} chunks")
        return chunks

    def _split_into_sections(self, text: str) -> List[Tuple[Optional[str], str]]:
        """Split document on article/section headers."""
        sections = []
        matches = list(self._section_re.finditer(text))

        if not matches:
            # No headers found — treat whole doc as one section
            return [(None, text)]

        # Text before first header
        if matches[0].start() > 0:
            preamble = text[:matches[0].start()].strip()
            if preamble:
                sections.append((None, preamble))

        # Each section: from header to next header
        for i, match in enumerate(matches):
            title = match.group(0).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            section_text = text[start:end].strip()
            if section_text:
                sections.append((title, section_text))

        return sections

    def _extract_tables(self, text: str, section_title: Optional[str], start_index: int) -> Tuple[List[TextChunk], str]:
        """Extract [TABLE]...[/TABLE] blocks as single chunks."""
        table_pattern = re.compile(r"\[TABLE\](.*?)\[/TABLE\]", re.DOTALL)
        tables = []
        chunk_index = start_index

        for match in table_pattern.finditer(text):
            table_content = match.group(1).strip()
            if table_content:
                tables.append(TextChunk(
                    content=f"[Table from {section_title or 'document'}]\n{table_content}",
                    chunk_index=chunk_index,
                    page_start=1,
                    page_end=1,
                    section_title=section_title,
                    chunk_type="table",
                    token_count=self._count_tokens(table_content),
                    raw_content=table_content,
                ))
                chunk_index += 1

        # Remove table blocks from text
        remaining = table_pattern.sub("", text).strip()
        return tables, remaining

    def _chunk_text(self, text: str, section_title: Optional[str], start_index: int) -> List[TextChunk]:
        """Split text into overlapping chunks respecting paragraph boundaries."""
        if not text.strip():
            return []

        # Split into paragraphs first
        paragraphs = [p.strip() for p in re.split(r"\n\n+", text) if p.strip()]

        chunks = []
        current_chunk = []
        current_tokens = 0
        chunk_index = start_index

        for para in paragraphs:
            para_tokens = self._count_tokens(para)

            # If single paragraph exceeds chunk size → split by sentences
            if para_tokens > self.chunk_size:
                # First flush current buffer
                if current_chunk:
                    content = "\n\n".join(current_chunk)
                    chunks.append(self._make_chunk(content, section_title, chunk_index))
                    chunk_index += 1
                    # Keep overlap: last sentence(s)
                    current_chunk = [self._get_overlap(content)]
                    current_tokens = self._count_tokens(current_chunk[0])

                # Split large paragraph by sentences
                sentence_chunks = self._split_by_sentences(para, section_title, chunk_index)
                chunks.extend(sentence_chunks)
                chunk_index += len(sentence_chunks)
                continue

            # Normal case: accumulate paragraphs
            if current_tokens + para_tokens > self.chunk_size and current_chunk:
                content = "\n\n".join(current_chunk)
                chunks.append(self._make_chunk(content, section_title, chunk_index))
                chunk_index += 1
                # Overlap: carry last paragraph
                overlap = self._get_overlap(content)
                current_chunk = [overlap] if overlap else []
                current_tokens = self._count_tokens(overlap)

            current_chunk.append(para)
            current_tokens += para_tokens

        # Flush remaining
        if current_chunk:
            content = "\n\n".join(current_chunk)
            chunks.append(self._make_chunk(content, section_title, chunk_index))

        return chunks

    def _split_by_sentences(self, text: str, section_title: Optional[str], start_index: int) -> List[TextChunk]:
        """Split text by sentences when paragraphs are too large."""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks = []
        current = []
        current_tokens = 0
        chunk_index = start_index

        for sent in sentences:
            sent_tokens = self._count_tokens(sent)
            if current_tokens + sent_tokens > self.chunk_size and current:
                content = " ".join(current)
                chunks.append(self._make_chunk(content, section_title, chunk_index))
                chunk_index += 1
                # Overlap
                overlap_sents = current[-2:] if len(current) >= 2 else current[-1:]
                current = overlap_sents
                current_tokens = sum(self._count_tokens(s) for s in current)
            current.append(sent)
            current_tokens += sent_tokens

        if current:
            chunks.append(self._make_chunk(" ".join(current), section_title, chunk_index))

        return chunks

    def _make_chunk(self, content: str, section_title: Optional[str], index: int) -> TextChunk:
        # Prepend section title to chunk for better retrieval context
        full_content = content
        if section_title:
            full_content = f"[{section_title}]\n{content}"
        return TextChunk(
            content=full_content,
            chunk_index=index,
            page_start=1,
            page_end=1,
            section_title=section_title,
            chunk_type="text",
            token_count=self._count_tokens(full_content),
            raw_content=content,
        )

    def _get_overlap(self, text: str) -> str:
        """Get last N tokens worth of text for overlap."""
        words = text.split()
        overlap_words = words[-self.chunk_overlap:] if len(words) > self.chunk_overlap else words
        return " ".join(overlap_words)

    def _count_tokens(self, text: str) -> int:
        """Approximate token count (1 token ≈ 4 chars for English)."""
        return max(1, len(text) // 4)

    def _assign_pages(self, chunks: List[TextChunk], pages: list) -> List[TextChunk]:
        """Assign approximate page numbers by matching chunk content to pages."""
        if not pages:
            return chunks
        total_pages = len(pages)
        total_chunks = len(chunks)
        if total_chunks == 0:
            return chunks
        # Simple proportional assignment
        for i, chunk in enumerate(chunks):
            page_idx = int(i / total_chunks * total_pages)
            chunk.page_start = pages[page_idx].page_number
            chunk.page_end = pages[min(page_idx + 1, total_pages - 1)].page_number
        return chunks


# Singleton
chunking_service = ChunkingService()