from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel


# ── Session ───────────────────────────────────────────────────────────────────

class SessionCreate(BaseModel):
    title:       str         = "New Chat"
    document_id: Optional[int] = None


class SessionUpdate(BaseModel):
    title: str


class SessionResponse(BaseModel):
    id:            int
    title:         str
    document_id:   Optional[int]  = None
    message_count: int            = 0
    last_message:  Optional[str]  = None
    is_active:     bool
    created_at:    datetime
    updated_at:    datetime

    model_config = {"from_attributes": True}


class SessionListResponse(BaseModel):
    sessions: List[SessionResponse]
    total:    int


# ── Message ───────────────────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    id:              int
    session_id:      int
    role:            str
    content:         str
    sources:         Optional[List[Any]] = None
    model_used:      Optional[str]       = None
    has_context:     bool                = False
    retrieval_score: Optional[float]     = None
    created_at:      datetime

    model_config = {"from_attributes": True}


# ── Chat request / response ───────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message:     str
    document_id: Optional[int] = None   # override session's document


class ChatResponse(BaseModel):
    session_id:      int
    message:         MessageResponse    # the assistant reply
    sources:         List[dict]  = []   # retrieved chunks used
    model_used:      str         = ""
    retrieval_score: float       = 0.0
    has_context:     bool        = False


class SessionDetailResponse(BaseModel):
    session:  SessionResponse
    messages: List[MessageResponse]