from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey, JSON
from db.database import Base


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = {"schema": "dbo"}

    id                = Column(Integer, primary_key=True, autoincrement=True)
    user_id           = Column(Integer, ForeignKey("dbo.users.id"), nullable=False, index=True)

    # File info
    filename          = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_size_bytes   = Column(Integer, nullable=True)
    mime_type         = Column(String(100), nullable=True)

    # Processing status
    status            = Column(String(50), default="uploaded")
    # uploaded → ocr_processing → chunking → embedding → ready → failed
    error_message     = Column(Text, nullable=True)

    # OCR results
    total_pages       = Column(Integer, nullable=True)
    total_chunks      = Column(Integer, nullable=True)
    ocr_confidence    = Column(Float, nullable=True)   # avg confidence 0-100
    language_detected = Column(String(20), nullable=True)

    # Document metadata (extracted from content)
    doc_metadata      = Column(JSON, nullable=True)    # title, parties, dates etc

    created_at        = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at        = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                               onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Document id={self.id} file={self.filename} status={self.status}>"


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = {"schema": "dbo"}

    id              = Column(Integer, primary_key=True, autoincrement=True)
    document_id     = Column(Integer, ForeignKey("dbo.documents.id"), nullable=False, index=True)

    # Chunk content
    chunk_index     = Column(Integer, nullable=False)   # order within document
    content         = Column(Text, nullable=False)       # cleaned text
    raw_content     = Column(Text, nullable=True)        # original OCR output

    # Location metadata
    page_start      = Column(Integer, nullable=True)
    page_end        = Column(Integer, nullable=True)
    section_title   = Column(String(500), nullable=True)  # e.g. "Article IX"
    chunk_type      = Column(String(50), default="text")  # text / table / header

    # Embedding
    embedding_id    = Column(String(100), nullable=True)  # ChromaDB doc ID
    is_embedded     = Column(Boolean, default=False)

    # Stats
    token_count     = Column(Integer, nullable=True)
    ocr_confidence  = Column(Float, nullable=True)

    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Chunk id={self.id} doc={self.document_id} idx={self.chunk_index}>"