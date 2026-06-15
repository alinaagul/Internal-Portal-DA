"""
celery_app/tasks.py
====================
Celery task: process_document
  Step 1 → OCR      (pdfplumber / tesseract)
  Step 2 → Chunking (section-aware)
  Step 3 → Embedding (Ollama mxbai-embed-large → ChromaDB)

Each step:
  - Updates document.status in SQL Server
  - Writes detailed logs via structured logger
  - On failure → marks document as "failed" with error_message
  - Retries up to 3x on transient errors (network, Ollama timeout)
"""

import logging
import time
from pathlib import Path
from typing import Optional

from celery import Task
from celery.utils.log import get_task_logger
from celery_app.celery_config import celery_app
from db.database import SessionLocal
import model  # noqa: F401 — ensures all models (User, Document, Chat) are registered with SQLAlchemy
from model.document import Document, DocumentChunk
from services.ocr_service import ocr_service
from services.chunking_service import chunking_service
from services.embedding_service import embedding_service

# Use Celery's task logger — output appears in the worker terminal
logger = get_task_logger(__name__)


# ── Helper: structured log line ───────────────────────────────────────────────

def log(task_id: str, doc_id: int, step: str, msg: str, level: str = "info"):
    prefix = f"[Task {task_id[:8]}] [Doc {doc_id}] [{step}]"
    line   = f"{prefix} {msg}"
    getattr(logger, level)(line)


# ── Helper: update DB status ──────────────────────────────────────────────────

def set_status(doc: Document, status: str, db, error: Optional[str] = None):
    doc.status        = status
    doc.error_message = error
    db.commit()


# ── Main Celery Task ──────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="celery_app.tasks.process_document",
    max_retries=3,
    default_retry_delay=15,
    throws=(FileNotFoundError,),   # don't retry if file is missing
)
def process_document(self, document_id: int, file_path: str) -> dict:
    """
    Full document processing pipeline.
    Called by FastAPI after upload — runs entirely in Celery worker.

    Args:
        document_id: DB primary key of the Document row
        file_path:   Absolute path to the saved PDF on disk

    Returns:
        dict with final stats (stored as Celery task result in Redis)
    """
    task_id = self.request.id or "local"
    db      = SessionLocal()

    try:
        # ── Fetch document row ────────────────────────────────────────────────
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise ValueError(f"Document {document_id} not found in DB")

        if not Path(file_path).exists():
            raise FileNotFoundError(f"File not found on disk: {file_path}")

        log(task_id, document_id, "INIT", f"Starting pipeline for '{doc.original_filename}'")
        log(task_id, document_id, "INIT", f"File size: {Path(file_path).stat().st_size / 1024:.1f} KB")

        # ══════════════════════════════════════════════════════════════════════
        # STEP 1: OCR
        # ══════════════════════════════════════════════════════════════════════
        t0 = time.time()
        set_status(doc, "ocr_processing", db)
        log(task_id, document_id, "OCR", "Starting OCR extraction...")

        self.update_state(state="PROGRESS", meta={
            "step": "ocr", "progress": 10,
            "message": "Extracting text from PDF..."
        })

        try:
            ocr_result = ocr_service.extract(file_path)
        except Exception as e:
            log(task_id, document_id, "OCR", f"Failed: {e}", level="error")
            raise self.retry(exc=e)

        # Write OCR stats to DB
        doc.total_pages               = ocr_result.total_pages
        doc.ocr_confidence            = round(ocr_result.avg_confidence, 2)
        doc.language_detected         = ocr_result.language
        doc.ocr_method                = ocr_result.extraction_method
        doc.pages_with_tables         = ocr_result.pages_with_tables
        doc.pages_with_low_confidence = ocr_result.pages_with_low_confidence
        db.commit()

        ocr_time = time.time() - t0
        log(task_id, document_id, "OCR",
            f"✓ Done in {ocr_time:.1f}s — "
            f"{ocr_result.total_pages} pages | "
            f"method={ocr_result.extraction_method} | "
            f"confidence={ocr_result.avg_confidence:.1f}% | "
            f"lang={ocr_result.language} | "
            f"tables_pages={doc.pages_with_tables} | "
            f"low_conf_pages={doc.pages_with_low_confidence}"
        )

        self.update_state(state="PROGRESS", meta={
            "step": "ocr", "progress": 35,
            "message": f"OCR done — {ocr_result.total_pages} pages extracted"
        })

        # ══════════════════════════════════════════════════════════════════════
        # STEP 2: CHUNKING
        # ══════════════════════════════════════════════════════════════════════
        t1 = time.time()
        set_status(doc, "chunking", db)
        log(task_id, document_id, "CHUNK", "Starting section-aware chunking...")

        self.update_state(state="PROGRESS", meta={
            "step": "chunking", "progress": 40,
            "message": "Splitting document into chunks..."
        })

        try:
            chunks = chunking_service.chunk(ocr_result.full_text, ocr_result.pages)
        except Exception as e:
            log(task_id, document_id, "CHUNK", f"Failed: {e}", level="error")
            raise self.retry(exc=e)

        if not chunks:
            raise ValueError("Chunking produced 0 chunks — document may be empty or unreadable")

        # Categorise chunks
        text_chunks  = [c for c in chunks if c.chunk_type == "text"]
        table_chunks = [c for c in chunks if c.chunk_type == "table"]
        log(task_id, document_id, "CHUNK",
            f"✓ {len(chunks)} total chunks — "
            f"{len(text_chunks)} text | {len(table_chunks)} table"
        )

        # Persist chunks to SQL Server
        log(task_id, document_id, "CHUNK", f"Saving {len(chunks)} chunks to SQL Server...")
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
                char_start     = chunk.char_start,
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

        # Update doc stats
        doc.total_chunks      = len(db_chunks)
        doc.text_chunk_count  = len(text_chunks)
        doc.table_chunk_count = len(table_chunks)
        db.commit()

        chunk_time = time.time() - t1
        log(task_id, document_id, "CHUNK",
            f"✓ Persisted in {chunk_time:.1f}s — "
            f"total={doc.total_chunks} | "
            f"text={doc.text_chunk_count} | "
            f"table={doc.table_chunk_count}"
        )

        self.update_state(state="PROGRESS", meta={
            "step": "chunking", "progress": 60,
            "message": f"Chunking done — {len(chunks)} chunks created"
        })

        # ══════════════════════════════════════════════════════════════════════
        # STEP 3: EMBEDDING
        # ══════════════════════════════════════════════════════════════════════
        t2 = time.time()
        set_status(doc, "embedding", db)
        log(task_id, document_id, "EMBED", "Checking Ollama availability...")

        self.update_state(state="PROGRESS", meta={
            "step": "embedding", "progress": 65,
            "message": "Connecting to Ollama..."
        })

        if not embedding_service.is_ollama_available():
            log(task_id, document_id, "EMBED",
                "⚠ Ollama not running — skipping embeddings. "
                "Start Ollama with: ollama serve",
                level="warning"
            )
            doc.embedding_status = "skipped_ollama_unavailable"
            db.commit()
        else:
            from core.config import settings
            log(task_id, document_id, "EMBED",
                f"Ollama ready. Model: {settings.OLLAMA_EMBED_MODEL} | "
                f"Chunks to embed: {len(db_chunks)}"
            )

            chunk_dicts = [
                {
                    "id":            c.id,
                    "chunk_index":   c.chunk_index,
                    "content":       c.content,
                    "section_title": c.section_title,
                    "page_start":    c.page_start,
                    "chunk_type":    c.chunk_type,
                }
                for c in db_chunks
            ]

            # Embed in batches with progress updates
            batch_size  = 10
            total       = len(chunk_dicts)
            success_all = 0
            failed_all  = 0

            for i in range(0, total, batch_size):
                batch   = chunk_dicts[i: i + batch_size]
                batch_n = i // batch_size + 1
                total_b = (total + batch_size - 1) // batch_size

                log(task_id, document_id, "EMBED",
                    f"Batch {batch_n}/{total_b} — "
                    f"chunks {i+1}–{min(i+batch_size, total)}/{total}"
                )

                try:
                    s, f = embedding_service.embed_chunks(document_id, batch, batch_size=batch_size)
                    success_all += s
                    failed_all  += f
                except Exception as e:
                    log(task_id, document_id, "EMBED",
                        f"Batch {batch_n} failed: {e}", level="warning")
                    failed_all += len(batch)

                # Update progress
                pct = 65 + int((i + batch_size) / total * 30)
                self.update_state(state="PROGRESS", meta={
                    "step":     "embedding",
                    "progress": min(pct, 95),
                    "message":  f"Embedding chunk {min(i+batch_size, total)}/{total}..."
                })

            # Mark embedded chunks in DB — commit in batches to avoid TCP timeout
            _BATCH = 50
            for i in range(0, len(db_chunks), _BATCH):
                for c in db_chunks[i:i + _BATCH]:
                    c.is_embedded  = True
                    c.embedding_id = f"doc{document_id}_chunk{c.chunk_index}"
                db.commit()

            doc.embedded_chunk_count = success_all
            doc.failed_embed_count   = failed_all
            doc.embedding_status     = (
                "complete" if failed_all == 0
                else f"partial_{success_all}_of_{total}"
            )
            db.commit()

            embed_time = time.time() - t2
            log(task_id, document_id, "EMBED",
                f"✓ Done in {embed_time:.1f}s — "
                f"embedded={success_all} | "
                f"failed={failed_all} | "
                f"status={doc.embedding_status}"
            )

        # ══════════════════════════════════════════════════════════════════════
        # DONE
        # ══════════════════════════════════════════════════════════════════════
        set_status(doc, "ready", db)
        total_time = time.time() - t0

        result = {
            "document_id":    document_id,
            "status":         "ready",
            "total_pages":    doc.total_pages,
            "total_chunks":   doc.total_chunks,
            "ocr_confidence": doc.ocr_confidence,
            "ocr_method":     doc.ocr_method,
            "embedded":       doc.embedded_chunk_count,
            "total_time_sec": round(total_time, 1),
            "message": (
                f"✅ Done in {total_time:.0f}s — "
                f"{doc.total_pages} pages → "
                f"{doc.total_chunks} chunks → "
                f"{doc.embedded_chunk_count} embedded"
            ),
        }

        log(task_id, document_id, "DONE", result["message"])
        return result

    except FileNotFoundError as e:
        # Don't retry — file is gone
        log(task_id, document_id, "ERROR", str(e), level="error")
        if db:
            doc = db.query(Document).filter(Document.id == document_id).first()
            if doc:
                set_status(doc, "failed", db, error=str(e))
        raise

    except Exception as e:
        log(task_id, document_id, "ERROR", f"Pipeline failed: {e}", level="error")
        if db:
            doc = db.query(Document).filter(Document.id == document_id).first()
            if doc:
                set_status(doc, "failed", db, error=str(e)[:500])
        raise

    finally:
        try:
            db.close()
        except Exception:
            pass