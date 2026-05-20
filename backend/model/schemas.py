from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator


# ── Signup ────────────────────────────────────────────────────────────────────
class UserCreate(BaseModel):
    full_name: str
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("full_name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Full name cannot be empty")
        return v.strip()


# ── Login ─────────────────────────────────────────────────────────────────────
class UserLogin(BaseModel):
    email: EmailStr
    password: str


# ── Response (never expose hashed_password) ───────────────────────────────────
class UserResponse(BaseModel):
    id: int
    full_name: str
    email: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Token ─────────────────────────────────────────────────────────────────────
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class TokenData(BaseModel):
    user_id: Optional[int] = None
    email: Optional[str] = None