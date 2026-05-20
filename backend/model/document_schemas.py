"""
document_schemas.py — Pydantic Response Schemas
=================================================
PURPOSE:
  Defines every request/response shape for the /documents endpoints.
  Pydantic validates types automatically so the API can't return
  half-populated responses when a field is None.

WHY THIS FILE EXISTS:
  FastAPI uses these to generate OpenAPI docs and to serialise ORM objects.
  The schemas here intentionally mirror the rich status format requested:

    {
      "document_id": 50,
      "filename": "contract.pdf",
      "status": "ready",
      "ocr": { "method": "pdfplumber", "total_pages": 12, ... },
      "chunking": { "total_chunks": 34, "text_chunks": 30, "table_chunks": 4 },
      "embedding": { "embedded_chunks": 34, "vector_index": "hnsw_cosine", ... },
      "chunks": [ { "chunk_index": 0, "page_number": 1, "text_preview": "..." } ]
    }
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


# ─── Upload ────────────────────────────────────────────────────────────────────

class DocumentUploadResponse(BaseModel):
    id: int
    filename: str
    original_filename: str
    status: str
    message: str

    model_config = {"from_attributes": True}


# ─── OCR sub-schema ────────────────────────────────────────────────────────────

class OCRStats(BaseModel):
    method: str = "pdfplumber"
    total_pages: int = 0
    avg_confidence_pct: float = 0.0
    pages_with_tables: int = 0
    pages_low_confidence: int = 0
    requires_review: bool = False


# ─── Chunking sub-schema ───────────────────────────────────────────────────────

class ChunkingStats(BaseModel):
    total_chunks: int = 0
    text_chunks: int = 0
    table_chunks: int = 0


# ─── Embedding sub-schema ─────────────────────────────────────────────────────

class EmbeddingStats(BaseModel):
    embedded_chunks: int = 0
    failed_chunks: int = 0
    vector_index: str = "hnsw_cosine"
    bm25_index: str = "rank_bm25"
    embedding_model: str = "mxbai-embed-large"


# ─── Chunk preview (used in status response) ──────────────────────────────────

class ChunkPreview(BaseModel):
    chunk_index: int
    page_number: int
    section_title: str = ""
    chunk_type: str
    token_count: Optional[int] = None
    text_preview: str                  # first 200 chars of content

    model_config = {"from_attributes": True}


# ─── Full status response ──────────────────────────────────────────────────────

class DocumentStatusResponse(BaseModel):
    """
    Returned by GET /documents/{id}/status
    Mirrors the requested rich format exactly.
    """
    document_id: int
    filename: str
    status: str
    language: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime

    ocr: OCRStats = OCRStats()
    chunking: ChunkingStats = ChunkingStats()
    embedding: EmbeddingStats = EmbeddingStats()
    chunks: List[ChunkPreview] = []
    message: str = ""

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_doc(cls, doc, chunks=None):
        """
        Build response from Document ORM object.
        Use this instead of model_validate when you have the ORM object.
        """
        chunk_previews = []
        if chunks:
            chunk_previews = [
                ChunkPreview(
                    chunk_index=c.chunk_index,
                    page_number=c.page_start or 1,
                    section_title=c.section_title or "",
                    chunk_type=c.chunk_type,
                    token_count=c.token_count,
                    text_preview=(c.content or "")[:200],
                )
                for c in chunks
            ]

        return cls(
            document_id=doc.id,
            filename=doc.original_filename,
            status=doc.status,
            language=doc.language_detected,
            error_message=doc.error_message,
            created_at=doc.created_at,
            ocr=OCRStats(
                method=doc.ocr_method or "pdfplumber",
                total_pages=doc.total_pages or 0,
                avg_confidence_pct=doc.ocr_confidence or 0.0,
                pages_with_tables=getattr(doc, "pages_with_tables", 0) or 0,
                pages_low_confidence=getattr(doc, "pages_with_low_confidence", 0) or 0,
                requires_review=(doc.ocr_confidence or 100) < 60,
            ),
            chunking=ChunkingStats(
                total_chunks=doc.total_chunks or 0,
                text_chunks=getattr(doc, "text_chunk_count", 0) or 0,
                table_chunks=getattr(doc, "table_chunk_count", 0) or 0,
            ),
            embedding=EmbeddingStats(
                embedded_chunks=getattr(doc, "embedded_chunk_count", 0) or 0,
                failed_chunks=getattr(doc, "failed_embed_count", 0) or 0,
            ),
            chunks=chunk_previews,
            message=(
                f"{doc.status.replace('_', ' ').title()} — "
                f"{doc.total_pages or '?'} pages, "
                f"{doc.total_chunks or '?'} chunks"
            ),
        )


# ─── List response ────────────────────────────────────────────────────────────

class DocumentListResponse(BaseModel):
    documents: List[DocumentStatusResponse]
    total: int


# ─── Individual chunk detail ──────────────────────────────────────────────────

class ChunkDetailResponse(BaseModel):
    id: int
    chunk_index: int
    content: str
    raw_content: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    section_title: Optional[str] = None
    chunk_type: str
    token_count: Optional[int] = None
    is_embedded: bool = False

    model_config = {"from_attributes": True}


# ─── Processing result (returned by background task on completion) ────────────

class ProcessingResult(BaseModel):
    document_id: int
    status: str
    total_pages: int
    total_chunks: int
    ocr_confidence: float
    message: str