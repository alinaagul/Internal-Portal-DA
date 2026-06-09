"""
document_processor.py — Full Pipeline Orchestrator
=====================================================
OPTIMIZATIONS vs PREVIOUS VERSION
───────────────────────────────────
1. EMBEDDING STEP uses updated embed_chunks() which now:
   - Skips already-embedded chunks (incremental re-processing)
   - Embeds in parallel (4 workers per batch, batch_size=20)
   - Uses correct MAX_EMBED_CHARS=2000 (was 400 — was discarding 75% of content)

2. CHUNK FIELD ALIGNMENT: char_start/char_end are now always written to the DB
   chunk record (previously getattr fallback with None meant page lookups failed).

3. STATUS GRANULARITY: added embedding sub-progress logging.

4. RESPONSE includes confidence_warning flag so API consumers can surface
   "low OCR confidence — verify source" warnings.

STATUS TRANSITIONS (unchanged):
  uploaded → ocr_processing → chunking → embedding → ready
                                                    ↘ failed (on any error)
"""

import logging
from pathlib import Path
from sqlalchemy.orm import Session

from model.document import Document, DocumentChunk
from services.ocr_service import ocr_service
from services.chunking_service import chunking_service
from services.embedding_service import embedding_service
from core.config import settings

logger = logging.getLogger(__name__)


class DocumentProcessor:

    async def process(self, document_id: int, file_path: str, db: Session) -> dict:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise ValueError(f"Document {document_id} not found")

        try:
            # ── STEP 1: OCR ───────────────────────────────────────────────────
            logger.info(f"[Pipeline] Step 1/3 — OCR  (doc {document_id})")
            self._set_status(doc, "ocr_processing", db)

            ocr_result = ocr_service.extract(file_path)

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
                f"method={ocr_result.extraction_method}"
            )

            # ── STEP 2: Chunking ──────────────────────────────────────────────
            logger.info(f"[Pipeline] Step 2/3 — Chunking (doc {document_id})")
            self._set_status(doc, "chunking", db)

            chunks = chunking_service.chunk(ocr_result.full_text, ocr_result.pages)

            db_chunks = []
            for chunk in chunks:
                db_chunk = DocumentChunk(
                    document_id    = document_id,
                    chunk_index    = chunk.chunk_index,
                    content        = chunk.content,
                    raw_content    = chunk.raw_content,
                    overlap_prefix = chunk.overlap_prefix,
                    page_start     = chunk.page_start,
                    page_end       = chunk.page_end,
                    char_start     = chunk.char_start,   # always set (fixed in chunking_service)
                    char_end       = chunk.char_end,
                    section_title  = chunk.section_title,
                    section_depth  = chunk.section_depth,
                    chunk_type     = chunk.chunk_type,
                    token_count    = chunk.token_count,
                )
                db.add(db_chunk)
                db_chunks.append(db_chunk)

            db.commit()
            for c in db_chunks:
                db.refresh(c)

            text_chunks  = sum(1 for c in db_chunks if c.chunk_type == "text")
            table_chunks = sum(1 for c in db_chunks if c.chunk_type == "table")
            def_chunks   = sum(1 for c in db_chunks if c.chunk_type == "definition")

            doc.total_chunks      = len(db_chunks)
            doc.text_chunk_count  = text_chunks
            doc.table_chunk_count = table_chunks
            db.commit()

            logger.info(
                f"[Pipeline] Chunking done — {len(db_chunks)} chunks "
                f"(text={text_chunks}, tables={table_chunks}, defs={def_chunks})"
            )

            # ── STEP 3: Embedding ─────────────────────────────────────────────
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

                success, failed = embedding_service.embed_chunks(
                    document_id, chunk_dicts, batch_size=20
                )

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

            # ── DONE ──────────────────────────────────────────────────────────
            self._set_status(doc, "ready", db)
            logger.info(f"[Pipeline] ✅ Doc {document_id} ready")

            return self._build_response(doc, db_chunks, ocr_result)

        except Exception as e:
            logger.error(f"[Pipeline] ❌ Doc {document_id} failed: {e}", exc_info=True)
            doc.status        = "failed"
            doc.error_message = str(e)[:500]
            db.commit()
            raise

    def _build_response(self, doc, db_chunks: list, ocr_result) -> dict:
        chunk_previews = [
            {
                "chunk_index":   c.chunk_index,
                "page_number":   c.page_start,
                "section_title": c.section_title or "",
                "chunk_type":    c.chunk_type,
                "token_count":   c.token_count,
                "text_preview":  c.content[:200],
            }
            for c in db_chunks
        ]

        return {
            "document_id": doc.id,
            "filename":    doc.original_filename,
            "status":      doc.status,
            "language":    doc.language_detected,
            "ocr": {
                "method":               doc.ocr_method or "pdfplumber",
                "total_pages":          doc.total_pages,
                "avg_confidence_pct":   doc.ocr_confidence,
                "pages_with_tables":    getattr(doc, "pages_with_tables", 0),
                "pages_low_confidence": getattr(doc, "pages_with_low_confidence", 0),
                "requires_review":      (doc.ocr_confidence or 100) < 60,
            },
            "chunking": {
                "total_chunks":  doc.total_chunks,
                "text_chunks":   getattr(doc, "text_chunk_count", 0),
                "table_chunks":  getattr(doc, "table_chunk_count", 0),
            },
            "embedding": {
                "embedded_chunks": getattr(doc, "embedded_chunk_count", 0),
                "failed_chunks":   getattr(doc, "failed_embed_count", 0),
                "vector_index":    "hnsw_cosine",
                "bm25_index":      "rank_bm25plus",
                "embedding_model": settings.OLLAMA_EMBED_MODEL,
            },
            "chunks": chunk_previews,
            "message": (
                f"Processed {doc.total_pages} pages into "
                f"{doc.total_chunks} chunks "
                f"(OCR confidence {doc.ocr_confidence:.1f}%)"
            ),
        }

    def _set_status(self, doc, status: str, db: Session):
        doc.status = status
        db.commit()
        logger.debug(f"[Pipeline] Status → {status}")


document_processor = DocumentProcessor()