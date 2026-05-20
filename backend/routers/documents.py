import os
import uuid
import asyncio
import logging
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, status
from sqlalchemy.orm import Session

from core.deps import get_current_user
from db.database import get_db
from model.user import User
from model.document import Document, DocumentChunk
from model.document_schemas import (
    DocumentUploadResponse,
    DocumentStatusResponse,
    DocumentListResponse,
    ChunkResponse,
)
from services.document_processor import document_processor
from services.embedding_service import embedding_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["Documents"])

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/tiff"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


# ── POST /documents/upload ────────────────────────────────────────────────────
@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Validate file type
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. Allowed: PDF, PNG, JPEG, TIFF",
        )

    # Read file and check size
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 50MB")

    # Save to disk with unique name
    ext = Path(file.filename).suffix.lower()
    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path = UPLOAD_DIR / unique_name

    with open(file_path, "wb") as f:
        f.write(contents)

    # Create DB record
    doc = Document(
        user_id=current_user.id,
        filename=unique_name,
        original_filename=file.filename,
        file_size_bytes=len(contents),
        mime_type=file.content_type,
        status="uploaded",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    logger.info(f"[Upload] Document {doc.id} saved — {file.filename} ({len(contents)//1024}KB)")

    # Kick off processing in background (non-blocking)
    background_tasks.add_task(_process_in_background, doc.id, str(file_path))

    return DocumentUploadResponse(
        id=doc.id,
        filename=doc.filename,
        original_filename=doc.original_filename,
        status=doc.status,
        message="File uploaded. Processing started in background.",
    )


async def _process_in_background(document_id: int, file_path: str):
    """Run the full OCR→chunk→embed pipeline in background."""
    from db.database import SessionLocal
    db = SessionLocal()
    try:
        await document_processor.process(document_id, file_path, db)
    except Exception as e:
        logger.error(f"[BG] Processing failed for doc {document_id}: {e}")
    finally:
        db.close()


# ── GET /documents ────────────────────────────────────────────────────────────
@router.get("/", response_model=DocumentListResponse)
def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    docs = (
        db.query(Document)
        .filter(Document.user_id == current_user.id)
        .order_by(Document.created_at.desc())
        .all()
    )
    return DocumentListResponse(
        documents=[DocumentStatusResponse.model_validate(d) for d in docs],
        total=len(docs),
    )


# ── GET /documents/{id}/status ───────────────────────────────────────────────
@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
def get_status(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = _get_doc_or_404(document_id, current_user.id, db)
    return DocumentStatusResponse.model_validate(doc)


# ── GET /documents/{id}/chunks ───────────────────────────────────────────────
@router.get("/{document_id}/chunks", response_model=list[ChunkResponse])
def get_chunks(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_doc_or_404(document_id, current_user.id, db)
    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
        .all()
    )
    return [ChunkResponse.model_validate(c) for c in chunks]


# ── DELETE /documents/{id} ───────────────────────────────────────────────────
@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = _get_doc_or_404(document_id, current_user.id, db)

    # Delete from ChromaDB
    embedding_service.delete_document(document_id)

    # Delete file from disk
    file_path = UPLOAD_DIR / doc.filename
    if file_path.exists():
        file_path.unlink()

    # Delete chunks + document from DB
    db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()
    db.delete(doc)
    db.commit()


# ── Helper ────────────────────────────────────────────────────────────────────
def _get_doc_or_404(document_id: int, user_id: int, db: Session) -> Document:
    doc = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == user_id,
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc