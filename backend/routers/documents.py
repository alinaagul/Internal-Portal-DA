import os
import uuid
import logging
from pathlib import Path
from fastapi import (
    APIRouter, Depends, HTTPException, UploadFile,
    File, BackgroundTasks, Query, status,
)
from sqlalchemy.orm import Session

from core.deps import get_current_user
from db.database import get_db
from model.user import User
from model.document import Document, DocumentChunk
from model.document_schemas import (
    DocumentUploadResponse,
    DocumentStatusResponse,
    DocumentListResponse,
    ChunkDetailResponse,
)
from services.document_processor import document_processor
from services.embedding_service import embedding_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["Documents"])

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/tiff"}
MAX_FILE_SIZE  = 50 * 1024 * 1024   # 50 MB


# ── POST /documents/upload ────────────────────────────────────────────────────

@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a PDF or image. Returns 202 immediately.
    Processing (OCR → chunk → embed) runs in background.
    Poll GET /documents/{id}/status to track progress.
    """
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported type: {file.content_type}. Allowed: PDF, PNG, JPEG, TIFF",
        )

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File exceeds 50 MB limit")

    # Save to disk with a UUID name to avoid collisions
    ext         = Path(file.filename).suffix.lower()
    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path   = UPLOAD_DIR / unique_name

    with open(file_path, "wb") as f:
        f.write(contents)

    # Create DB record (status = "uploaded")
    doc = Document(
        user_id           = current_user.id,
        filename          = unique_name,
        original_filename = file.filename,
        file_size_bytes   = len(contents),
        mime_type         = file.content_type,
        status            = "uploaded",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    logger.info(f"[Upload] Doc {doc.id} saved — {file.filename} ({len(contents)//1024} KB)")

    # Kick off background processing (non-blocking)
    background_tasks.add_task(_run_pipeline, doc.id, str(file_path))

    return DocumentUploadResponse(
        id                = doc.id,
        filename          = doc.filename,
        original_filename = doc.original_filename,
        status            = doc.status,
        message           = "Uploaded. Pipeline started: OCR → Chunking → Embedding.",
    )


async def _run_pipeline(document_id: int, file_path: str):
    """Background task — runs outside the request lifecycle."""
    from db.database import SessionLocal
    db = SessionLocal()
    try:
        await document_processor.process(document_id, file_path, db)
    except Exception as e:
        logger.error(f"[BG] Pipeline failed for doc {document_id}: {e}")
    finally:
        db.close()


# ── GET /documents/ ───────────────────────────────────────────────────────────

@router.get("/", response_model=DocumentListResponse)
def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all documents for the authenticated user, newest first."""
    docs = (
        db.query(Document)
        .filter(Document.user_id == current_user.id)
        .order_by(Document.created_at.desc())
        .all()
    )
    return DocumentListResponse(
        documents=[DocumentStatusResponse.from_orm_doc(d) for d in docs],
        total=len(docs),
    )


# ── GET /documents/{id}/status ───────────────────────────────────────────────

@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
def get_status(
    document_id: int,
    include_chunks: bool = Query(default=True, description="Include chunk previews in response"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Full status + stats for a document.
    Returns OCR stats, chunking breakdown, embedding stats, and chunk previews.
    
    include_chunks=false omits the chunks array (lighter response for polling).
    """
    doc = _get_doc_or_404(document_id, current_user.id, db)

    chunks = None
    if include_chunks and doc.status == "ready":
        chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
            .all()
        )

    return DocumentStatusResponse.from_orm_doc(doc, chunks)


# ── GET /documents/{id}/chunks ───────────────────────────────────────────────

@router.get("/{document_id}/chunks", response_model=list[ChunkDetailResponse])
def get_chunks(
    document_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    chunk_type: str = Query(default=None, description="Filter by 'text' or 'table'"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Paginated list of chunks for a document.
    Optionally filter by chunk_type (text | table).
    """
    _get_doc_or_404(document_id, current_user.id, db)

    q = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id)

    if chunk_type:
        q = q.filter(DocumentChunk.chunk_type == chunk_type)

    chunks = (
        q.order_by(DocumentChunk.chunk_index)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return [ChunkDetailResponse.model_validate(c) for c in chunks]


# ── DELETE /documents/{id} ───────────────────────────────────────────────────

@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete a document and ALL associated data:
    - SQL rows (document + chunks)
    - ChromaDB vector collection
    - BM25 in-memory cache
    - Uploaded file from disk
    """
    doc = _get_doc_or_404(document_id, current_user.id, db)

    # 1. Remove vectors + BM25 cache
    embedding_service.delete_document(document_id)

    # 2. Remove uploaded file
    file_path = UPLOAD_DIR / doc.filename
    if file_path.exists():
        file_path.unlink()

    # 3. Remove DB rows
    db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()
    db.delete(doc)
    db.commit()

    logger.info(f"[Delete] Doc {document_id} fully removed")


# ── Helper ────────────────────────────────────────────────────────────────────

def _get_doc_or_404(document_id: int, user_id: int, db: Session) -> Document:
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.user_id == user_id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc