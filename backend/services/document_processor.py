"""
document_processor.py — Full Pipeline Orchestrator
=====================================================
PURPOSE:
  Runs the complete 3-step pipeline for every uploaded document:
    Step 1: OCR  (ocr_service)   → raw text per page + confidence + tables
    Step 2: Chunk (chunking_service) → semantic chunks with overlap
    Step 3: Embed (embedding_service) → HNSW vectors + BM25 index

  Writes granular status updates to SQL Server at every step so the
  status API always reflects exactly where processing is.

WHY THIS FILE EXISTS:
  FastAPI cannot run heavy IO (OCR, Ollama calls) synchronously in a request.
  This processor runs in a BackgroundTask. Every intermediate result is
  persisted to DB so the frontend can poll /documents/{id}/status and see
  live progress including chunk counts, OCR confidence, and any errors.

STATUS TRANSITIONS:
  uploaded → ocr_processing → chunking → embedding → ready
                                                    ↘ failed (on any error)

OLLAMA MODELS: Delegated to embedding_service (mxbai-embed-large for embeddings,
  mistral:7b-instruct for query expansion — not called here).
"""

import logging
from pathlib import Path
from sqlalchemy.orm import Session

from model.document import Document, DocumentChunk
from services.ocr_service import ocr_service
from services.chunking_service import chunking_service
from services.embedding_service import embedding_service

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """
    Full pipeline orchestrator.
    Call: await document_processor.process(document_id, file_path, db)
    """

    async def process(self, document_id: int, file_path: str, db: Session) -> dict:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise ValueError(f"Document {document_id} not found")

        try:
            # ────────────────────────────────────────────────────────────────
            # STEP 1 — OCR
            # ────────────────────────────────────────────────────────────────
            logger.info(f"[Pipeline] Step 1/3 — OCR  (doc {document_id})")
            self._set_status(doc, "ocr_processing", db)

            ocr_result = ocr_service.extract(file_path)

            # Persist OCR-level stats immediately (visible in status endpoint)
            doc.total_pages               = ocr_result.total_pages
            doc.ocr_confidence            = round(ocr_result.avg_confidence, 2)
            doc.language_detected         = ocr_result.language
            doc.ocr_method                = ocr_result.extraction_method
            doc.pages_with_tables         = ocr_result.pages_with_tables
            doc.pages_with_low_confidence = ocr_result.pages_with_low_confidence
            db.commit()

            logger.info(
                f"[Pipeline] OCR done — {ocr_result.total_pages} pages | "
                f"avg_conf={ocr_result.avg_confidence:.1f}% | "
                f"method={ocr_result.extraction_method} | "
                f"tables_on={ocr_result.pages_with_tables} pages"
            )

            # ────────────────────────────────────────────────────────────────
            # STEP 2 — Chunking
            # ────────────────────────────────────────────────────────────────
            logger.info(f"[Pipeline] Step 2/3 — Chunking (doc {document_id})")
            self._set_status(doc, "chunking", db)

            chunks = chunking_service.chunk(ocr_result.full_text, ocr_result.pages)

            # Persist every chunk to SQL Server
            db_chunks = []
            for chunk in chunks:
                db_chunk = DocumentChunk(
                    document_id    = document_id,
                    chunk_index    = chunk.chunk_index,
                    content        = chunk.content,
                    raw_content    = chunk.raw_content,
                    overlap_prefix = getattr(chunk, "overlap_prefix", ""),
                    page_start     = chunk.page_start,
                    page_end       = chunk.page_end,
                    char_start     = getattr(chunk, "char_start", None),
                    char_end       = getattr(chunk, "char_end", None),
                    section_title  = chunk.section_title,
                    section_depth  = getattr(chunk, "section_depth", 0),
                    chunk_type     = chunk.chunk_type,
                    token_count    = chunk.token_count,
                )
                db.add(db_chunk)
                db_chunks.append(db_chunk)

            db.commit()
            for c in db_chunks:
                db.refresh(c)  # populate auto-generated IDs

            # Count by type for the API response
            text_chunks  = sum(1 for c in db_chunks if c.chunk_type == "text")
            table_chunks = sum(1 for c in db_chunks if c.chunk_type == "table")

            doc.total_chunks        = len(db_chunks)
            doc.text_chunk_count    = text_chunks
            doc.table_chunk_count   = table_chunks
            db.commit()

            logger.info(
                f"[Pipeline] Chunking done — {len(db_chunks)} chunks "
                f"(text={text_chunks}, tables={table_chunks})"
            )

            # ────────────────────────────────────────────────────────────────
            # STEP 3 — Embedding (Vector HNSW + BM25)
            # ────────────────────────────────────────────────────────────────
            logger.info(f"[Pipeline] Step 3/3 — Embedding (doc {document_id})")
            self._set_status(doc, "embedding", db)

            if not embedding_service.is_ollama_available():
                logger.warning(
                    "[Pipeline] Ollama not available — skipping embeddings.\n"
                    "  → Start Ollama: ollama serve\n"
                    "  → Pull model : ollama pull mxbai-embed-large"
                )
                doc.embedding_status = "skipped_ollama_unavailable"
                db.commit()
            else:
                chunk_dicts = [
                    {
                        "id":            c.id,
                        "chunk_index":   c.chunk_index,
                        "content":       c.content,
                        "raw_content":   c.raw_content,
                        "section_title": c.section_title,
                        "page_start":    c.page_start,
                        "chunk_type":    c.chunk_type,
                    }
                    for c in db_chunks
                ]

                success, failed = embedding_service.embed_chunks(document_id, chunk_dicts)

                # Mark embedded chunks in SQL
                for c in db_chunks:
                    c.is_embedded  = True
                    c.embedding_id = f"doc{document_id}_chunk{c.chunk_index}"
                db.commit()

                doc.embedded_chunk_count = success
                doc.failed_embed_count   = failed
                db.commit()

                logger.info(
                    f"[Pipeline] Embedding done — "
                    f"{success}/{len(db_chunks)} succeeded, {failed} failed"
                )

            # ────────────────────────────────────────────────────────────────
            # DONE
            # ────────────────────────────────────────────────────────────────
            self._set_status(doc, "ready", db)
            logger.info(f"[Pipeline] ✅ Doc {document_id} ready")

            return self._build_response(doc, db_chunks, ocr_result)

        except Exception as e:
            logger.error(f"[Pipeline] ❌ Doc {document_id} failed: {e}", exc_info=True)
            doc.status        = "failed"
            doc.error_message = str(e)[:500]
            db.commit()
            raise

    # ── Response builder — matches the rich format requested ──────────────────

    def _build_response(self, doc: Document, db_chunks: list, ocr_result) -> dict:
        """
        Build the detailed API response dict.
        This is what /documents/{id}/status returns once processing is complete.

        Matches the requested format:
          document_id, status, total_pages, total_chunks, ocr_confidence,
          language, chunk_type_breakdown, ocr_stats, embedding_stats,
          + preview of each chunk (chunk_index, page, text_preview)
        """
        chunk_previews = [
            {
                "chunk_index":  c.chunk_index,
                "page_number":  c.page_start,
                "section_title": c.section_title or "",
                "chunk_type":   c.chunk_type,
                "token_count":  c.token_count,
                "text_preview": c.content[:200],   # first 200 chars
            }
            for c in db_chunks
        ]

        return {
            # ── Identity ──────────────────────────────────────────────
            "document_id":           doc.id,
            "filename":              doc.original_filename,
            "status":                doc.status,
            "language":              doc.language_detected,

            # ── OCR stats ─────────────────────────────────────────────
            "ocr": {
                "method":                doc.ocr_method or "pdfplumber",
                "total_pages":           doc.total_pages,
                "avg_confidence_pct":    doc.ocr_confidence,
                "pages_with_tables":     getattr(doc, "pages_with_tables", 0),
                "pages_low_confidence":  getattr(doc, "pages_with_low_confidence", 0),
                "requires_review":       (doc.ocr_confidence or 100) < 60,
            },

            # ── Chunking stats ────────────────────────────────────────
            "chunking": {
                "total_chunks":   doc.total_chunks,
                "text_chunks":    getattr(doc, "text_chunk_count", 0),
                "table_chunks":   getattr(doc, "table_chunk_count", 0),
            },

            # ── Embedding stats ───────────────────────────────────────
            "embedding": {
                "embedded_chunks":     getattr(doc, "embedded_chunk_count", 0),
                "failed_chunks":       getattr(doc, "failed_embed_count", 0),
                "vector_index":        "hnsw_cosine",
                "bm25_index":          "rank_bm25",
                "embedding_model":     "mxbai-embed-large",
            },

            # ── Chunk previews ────────────────────────────────────────
            "chunks": chunk_previews,

            "message": (
                f"Processed {doc.total_pages} pages into "
                f"{doc.total_chunks} chunks "
                f"(OCR confidence {doc.ocr_confidence:.1f}%)"
            ),
        }

    def _set_status(self, doc: Document, status: str, db: Session):
        doc.status = status
        db.commit()
        logger.debug(f"[Pipeline] Status → {status}")


# Singleton
document_processor = DocumentProcessor()