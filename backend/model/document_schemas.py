from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    id: int
    filename: str
    original_filename: str
    status: str
    message: str
    total_pages: Optional[int] = None

    model_config = {"from_attributes": True}


class DocumentStatusResponse(BaseModel):
    id: int
    original_filename: str
    status: str
    total_pages: Optional[int] = None
    total_chunks: Optional[int] = None
    ocr_confidence: Optional[float] = None
    language_detected: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    documents: List[DocumentStatusResponse]
    total: int


class ChunkResponse(BaseModel):
    id: int
    chunk_index: int
    content: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    section_title: Optional[str] = None
    chunk_type: str
    token_count: Optional[int] = None

    model_config = {"from_attributes": True}


class ProcessingResult(BaseModel):
    document_id: int
    status: str
    total_pages: int
    total_chunks: int
    ocr_confidence: float
    message: str