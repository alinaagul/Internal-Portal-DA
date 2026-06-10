from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON, Float
from db.database import Base


class ChatSession(Base):
    __tablename__  = "chat_sessions"
    __table_args__ = {"schema": "dbo"}

    id          = Column(Integer, primary_key=True, autoincrement=True)
    user_id     = Column(Integer, ForeignKey("dbo.users.id"),     nullable=False, index=True)
    document_id = Column(Integer, ForeignKey("dbo.documents.id"), nullable=True,  index=True)

    title       = Column(String(500), nullable=False, default="New Chat")
    is_active   = Column(Boolean, default=True)

    # Stats
    message_count = Column(Integer, default=0)
    last_message  = Column(Text,    nullable=True)   # preview of last message

    # Memory management: running summary of older messages outside the rolling window
    context_summary = Column(Text, nullable=True)

    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at  = Column(DateTime,
                         default=lambda:  datetime.now(timezone.utc),
                         onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<ChatSession id={self.id} title={self.title!r}>"


class ChatMessage(Base):
    __tablename__  = "chat_messages"
    __table_args__ = {"schema": "dbo"}

    id         = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("dbo.chat_sessions.id"), nullable=False, index=True)

    role       = Column(String(20),  nullable=False)   # "user" | "assistant"
    content    = Column(Text,        nullable=False)

    # RAG metadata (filled for assistant messages)
    sources         = Column(JSON,    nullable=True)   # list of chunk references
    model_used      = Column(String(100), nullable=True)
    tokens_used     = Column(Integer, nullable=True)
    retrieval_score = Column(Float,   nullable=True)   # top chunk relevance score
    has_context     = Column(Boolean, default=False)   # was RAG context used?

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<ChatMessage id={self.id} role={self.role} session={self.session_id}>"