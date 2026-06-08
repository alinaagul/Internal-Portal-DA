"""
document.py — SQLAlchemy ORM Models
=====================================
PURPOSE:
  Defines the two core DB tables:
    1. documents       — one row per uploaded file
    2. document_chunks — one row per chunk produced from a document

WHY THIS FILE EXISTS:
  All pipeline stages write to these tables. The status endpoint reads from
  them. Every metric the API should surface (ocr_confidence, chunk counts,
  embedding status, etc.) lives here as a proper column so the status response
  is built from DB data, not from in-memory state.

NEW COLUMNS vs original (added for rich API response tracking):
  documents:
    - ocr_method                (pdfplumber | tesseract)
    - pages_with_tables         (int)
    - pages_with_low_confidence (int)
    - text_chunk_count          (int)
    - table_chunk_count         (int)
    - embedded_chunk_count      (int)
    - failed_embed_count        (int)
    - embedding_status          (str)

  document_chunks:
    - raw_content               (Text)    — plain text for BM25 index
    - overlap_prefix            (Text)    — sliding-window overlap text from previous chunk
    - char_start                (Integer) — byte offset of chunk start in OCR full_text
    - char_end                  (Integer) — byte offset of chunk end in OCR full_text
    - section_depth             (Integer) — 0=article, 1=section, 2=subsection

MIGRATION NOTE:
  If upgrading an existing DB, run the Alembic migration (or manual ALTER TABLE):

    ALTER TABLE dbo.document_chunks ADD overlap_prefix NVARCHAR(MAX) NULL;
    ALTER TABLE dbo.document_chunks ADD char_start     INT           NULL;
    ALTER TABLE dbo.document_chunks ADD char_end       INT           NULL;
    ALTER TABLE dbo.document_chunks ADD section_depth  INT           NULL DEFAULT 0;

NOTHING is stored locally that doesn't belong in DB.
No JSON files. No pickle files. No local state outside SQL + ChromaDB.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean,
    DateTime, ForeignKey, JSON,
)
from db.database import Base


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = {"schema": "dbo"}

    # ── Identity ───────────────────────────────────────────────────────────────
    id                = Column(Integer, primary_key=True, autoincrement=True)
    user_id           = Column(Integer, ForeignKey("dbo.users.id"), nullable=False, index=True)

    # ── File info ──────────────────────────────────────────────────────────────
    filename          = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_size_bytes   = Column(Integer, nullable=True)
    mime_type         = Column(String(100), nullable=True)

    # ── Pipeline status ────────────────────────────────────────────────────────
    # Flow: uploaded → ocr_processing → chunking → embedding → ready | failed
    status            = Column(String(50), default="uploaded")
    error_message     = Column(Text, nullable=True)

    # ── OCR stats (written at Step 1) ─────────────────────────────────────────
    total_pages               = Column(Integer,  nullable=True)
    ocr_confidence            = Column(Float,    nullable=True)   # avg 0–100
    language_detected         = Column(String(20), nullable=True)
    ocr_method                = Column(String(50),  nullable=True)  # pdfplumber | tesseract
    pages_with_tables         = Column(Integer,  nullable=True, default=0)
    pages_with_low_confidence = Column(Integer,  nullable=True, default=0)

    # ── Chunking stats (written at Step 2) ────────────────────────────────────
    total_chunks      = Column(Integer, nullable=True)
    text_chunk_count  = Column(Integer, nullable=True, default=0)
    table_chunk_count = Column(Integer, nullable=True, default=0)

    # ── Embedding stats (written at Step 3) ───────────────────────────────────
    embedded_chunk_count = Column(Integer, nullable=True, default=0)
    failed_embed_count   = Column(Integer, nullable=True, default=0)
    embedding_status     = Column(String(100), nullable=True)  # e.g. "skipped_ollama_unavailable"

    # ── Extracted metadata (optional, from LLM summary) ───────────────────────
    doc_metadata      = Column(JSON, nullable=True)   # parties, dates, etc.

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return f"<Document id={self.id} file={self.original_filename!r} status={self.status}>"


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = {"schema": "dbo"}

    # ── Identity ───────────────────────────────────────────────────────────────
    id          = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(
        Integer, ForeignKey("dbo.documents.id"), nullable=False, index=True
    )

    # ── Content ────────────────────────────────────────────────────────────────
    chunk_index    = Column(Integer, nullable=False)    # order within document
    content        = Column(Text, nullable=False)        # section-prefixed → embedding
    raw_content    = Column(Text, nullable=True)         # plain body → BM25
    overlap_prefix = Column(Text, nullable=True)         # trailing text from previous chunk (sliding window)

    # ── Location ──────────────────────────────────────────────────────────────
    page_start    = Column(Integer,     nullable=True)
    page_end      = Column(Integer,     nullable=True)
    char_start    = Column(Integer,     nullable=True)   # byte offset into OCR full_text
    char_end      = Column(Integer,     nullable=True)   # byte offset into OCR full_text
    section_title = Column(String(500), nullable=True)   # e.g. "ARTICLE IX – TERMINATION"
    section_depth = Column(Integer,     nullable=True, default=0)  # 0=article, 1=section, 2=subsection
    chunk_type    = Column(String(50),  default="text")  # text | table | header | definition

    # ── Embedding ─────────────────────────────────────────────────────────────
    embedding_id  = Column(String(100), nullable=True)   # ChromaDB document ID
    is_embedded   = Column(Boolean, default=False)

    # ── Stats ─────────────────────────────────────────────────────────────────
    token_count    = Column(Integer, nullable=True)
    ocr_confidence = Column(Float,   nullable=True)      # per-chunk if needed

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return (
            f"<Chunk id={self.id} doc={self.document_id} "
            f"idx={self.chunk_index} type={self.chunk_type}>"
        )