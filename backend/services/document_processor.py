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
    Full pipeline orchestrator:
    PDF → OCR → Chunking → Embedding → ChromaDB
    Status updates written to SQL Server throughout.
    """

    async def process(self, document_id: int, file_path: str, db: Session) -> dict:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise ValueError(f"Document {document_id} not found")

        try:
            # ── Step 1: OCR ──────────────────────────────────────────────────
            logger.info(f"[Pipeline] Step 1/3 — OCR for doc {document_id}")
            self._set_status(doc, "ocr_processing", db)

            ocr_result = ocr_service.extract(file_path)

            doc.total_pages = ocr_result.total_pages
            doc.ocr_confidence = round(ocr_result.avg_confidence, 2)
            doc.language_detected = ocr_result.language
            db.commit()

            # ── Step 2: Chunking ──────────────────────────────────────────────
            logger.info(f"[Pipeline] Step 2/3 — Chunking doc {document_id}")
            self._set_status(doc, "chunking", db)

            chunks = chunking_service.chunk(ocr_result.full_text, ocr_result.pages)

            # Persist chunks to SQL Server
            db_chunks = []
            for chunk in chunks:
                db_chunk = DocumentChunk(
                    document_id=document_id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    raw_content=chunk.raw_content,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    section_title=chunk.section_title,
                    chunk_type=chunk.chunk_type,
                    token_count=chunk.token_count,
                )
                db.add(db_chunk)
                db_chunks.append(db_chunk)

            db.commit()
            # Refresh to get IDs
            for c in db_chunks:
                db.refresh(c)

            doc.total_chunks = len(db_chunks)
            db.commit()

            # ── Step 3: Embedding ─────────────────────────────────────────────
            logger.info(f"[Pipeline] Step 3/3 — Embedding doc {document_id}")
            self._set_status(doc, "embedding", db)

            if embedding_service.is_ollama_available():
                chunk_dicts = [
                    {
                        "id": c.id,
                        "chunk_index": c.chunk_index,
                        "content": c.content,
                        "section_title": c.section_title,
                        "page_start": c.page_start,
                        "chunk_type": c.chunk_type,
                    }
                    for c in db_chunks
                ]

                success, failed = embedding_service.embed_chunks(document_id, chunk_dicts)

                # Mark embedded chunks
                for c in db_chunks:
                    c.is_embedded = True
                    c.embedding_id = f"doc{document_id}_chunk{c.chunk_index}"
                db.commit()

                logger.info(f"[Pipeline] Embedded {success}/{len(db_chunks)} chunks")
            else:
                logger.warning("[Pipeline] Ollama not available — skipping embeddings. Run: ollama serve")

            # ── Done ──────────────────────────────────────────────────────────
            self._set_status(doc, "ready", db)
            logger.info(f"[Pipeline] ✅ Document {document_id} ready — {doc.total_chunks} chunks")

            return {
                "document_id": document_id,
                "status": "ready",
                "total_pages": doc.total_pages,
                "total_chunks": doc.total_chunks,
                "ocr_confidence": doc.ocr_confidence,
                "language": doc.language_detected,
                "message": f"Processed {doc.total_pages} pages into {doc.total_chunks} chunks",
            }

        except Exception as e:
            logger.error(f"[Pipeline] ❌ Failed for doc {document_id}: {e}")
            doc.status = "failed"
            doc.error_message = str(e)[:500]
            db.commit()
            raise

    def _set_status(self, doc: Document, status: str, db: Session):
        doc.status = status
        db.commit()


document_processor = DocumentProcessor()