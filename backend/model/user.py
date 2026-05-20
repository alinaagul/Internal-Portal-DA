from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from db.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "dbo"}

    id            = Column(Integer, primary_key=True, index=True, autoincrement=True)
    full_name     = Column(String(150), nullable=False)
    email         = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active     = Column(Boolean, default=True, nullable=False)
    created_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at    = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return f"<User id={self.id} email={self.email}>"