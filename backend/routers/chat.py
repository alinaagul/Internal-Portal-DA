"""
routers/chat.py
================
Endpoints:
  POST   /chat/sessions              — create session
  GET    /chat/sessions              — list all sessions
  GET    /chat/sessions/{id}         — get session + messages
  PATCH  /chat/sessions/{id}/title   — update title
  DELETE /chat/sessions/{id}         — delete session
  POST   /chat/sessions/{id}/message — send message → get AI reply
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.deps import get_current_user
from db.database import get_db
from model.user import User
from model.document import Document
from model.chat import ChatSession, ChatMessage
from model.chat_schemas import (
    SessionCreate, SessionUpdate, SessionResponse,
    SessionListResponse, SessionDetailResponse,
    ChatRequest, ChatResponse, MessageResponse,
)
from services.chat_service import chat_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["Chat"])


# ── POST /chat/sessions ───────────────────────────────────────────────────────
@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def create_session(
    payload:      SessionCreate,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    # Validate document belongs to user (if provided)
    if payload.document_id:
        _get_doc_or_404(payload.document_id, current_user.id, db)

    session = ChatSession(
        user_id     = current_user.id,
        document_id = payload.document_id,
        title       = payload.title or "New Chat",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    logger.info(f"[Chat] Session {session.id} created for user {current_user.id}")
    return SessionResponse.model_validate(session)


# ── GET /chat/sessions ────────────────────────────────────────────────────────
@router.get("/sessions", response_model=SessionListResponse)
def list_sessions(
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == current_user.id, ChatSession.is_active == True)
        .order_by(ChatSession.updated_at.desc())
        .all()
    )
    return SessionListResponse(
        sessions=[SessionResponse.model_validate(s) for s in sessions],
        total=len(sessions),
    )


# ── GET /chat/sessions/{id} ───────────────────────────────────────────────────
@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
def get_session(
    session_id:   int,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    session  = _get_session_or_404(session_id, current_user.id, db)
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return SessionDetailResponse(
        session  = SessionResponse.model_validate(session),
        messages = [MessageResponse.model_validate(m) for m in messages],
    )


# ── PATCH /chat/sessions/{id}/title ──────────────────────────────────────────
@router.patch("/sessions/{session_id}/title", response_model=SessionResponse)
def update_title(
    session_id:   int,
    payload:      SessionUpdate,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    session       = _get_session_or_404(session_id, current_user.id, db)
    session.title = payload.title.strip() or "New Chat"
    db.commit()
    db.refresh(session)
    return SessionResponse.model_validate(session)


# ── DELETE /chat/sessions/{id} ────────────────────────────────────────────────
@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id:   int,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    session           = _get_session_or_404(session_id, current_user.id, db)
    session.is_active = False   # soft delete
    db.commit()


# ── POST /chat/sessions/{id}/message ─────────────────────────────────────────
@router.post("/sessions/{session_id}/message", response_model=ChatResponse)
def send_message(
    session_id:   int,
    payload:      ChatRequest,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    db_session = _get_session_or_404(session_id, current_user.id, db)

    # Determine which document to use
    doc_id = payload.document_id or db_session.document_id
    if doc_id:
        doc = db.query(Document).filter(
            Document.id == doc_id,
            Document.user_id == current_user.id,
            Document.status == "ready",
        ).first()
        if not doc:
            doc_id = None

    # Save user message
    user_msg = ChatMessage(
        session_id=session_id,
        role="user",
        content=payload.message,
    )
    db.add(user_msg)
    db.commit()

    # Build the in-memory ChatSession the service expects
    from services.chat_service import ChatSession as ServiceSession, Message as ServiceMessage

    history_rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )

    svc_session = ServiceSession(
        session_id=str(session_id),
        document_id=doc_id,
        user_id=current_user.id,
    )
    # Populate history (exclude the message we just added)
    for row in history_rows[:-1]:
        svc_session.messages.append(
            ServiceMessage(role=row.role, content=row.content)
        )

    # Generate AI answer
    logger.info(f"[Chat] Generating answer — session={session_id} doc={doc_id}")
    result = chat_service.answer(
        session=svc_session,
        query=payload.message,
    )

    answer    = result["answer"]
    raw_sources   = result["sources"]
    sources = []
    for s in raw_sources:
        if isinstance(s, dict):
            sources.append(s)
        elif isinstance(s, str):
            # Parse "Title — Page X" format
            if " — " in s:
                parts = s.split(" — ", 1)
                sources.append({"title": parts[0].strip(), "page": parts[1].strip()})
            else:
                sources.append({"title": s, "page": ""})
    scores = result.get("hybrid_scores") or []
    top_score = scores[0]["hybrid"] if scores else 0.0

    # Save assistant message
    assistant_msg = ChatMessage(
        session_id=session_id,
        role="assistant",
        content=answer,
        sources=sources,
        model_used=chat_service.__class__.__name__,
        retrieval_score=top_score,
        has_context=len(sources) > 0,
    )
    db.add(assistant_msg)

    # Auto-generate title from first message (simple fallback — no generate_title method)
    if (db_session.message_count or 0) == 0:
        db_session.title = payload.message[:60]  # use first 60 chars as title

    # Update session stats
    db_session.message_count = (db_session.message_count or 0) + 2
    db_session.last_message  = answer[:200]
    if doc_id:
        db_session.document_id = doc_id

    db.commit()
    db.refresh(assistant_msg)

    return ChatResponse(
        session_id=session_id,
        message=MessageResponse.model_validate(assistant_msg),
        sources=sources,
        model_used=str(assistant_msg.model_used),
        retrieval_score=top_score,
        has_context=len(sources) > 0,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────
def _get_session_or_404(session_id: int, user_id: int, db: Session) -> ChatSession:
    s = db.query(ChatSession).filter(
        ChatSession.id      == session_id,
        ChatSession.user_id == user_id,
        ChatSession.is_active == True,
    ).first()
    if not s:
        raise HTTPException(404, "Chat session not found")
    return s


def _get_doc_or_404(document_id: int, user_id: int, db: Session) -> Document:
    d = db.query(Document).filter(
        Document.id      == document_id,
        Document.user_id == user_id,
    ).first()
    if not d:
        raise HTTPException(404, "Document not found")
    return d