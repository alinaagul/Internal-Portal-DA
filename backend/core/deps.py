"""
deps.py — FastAPI Auth Dependency
===================================
FIX APPLIED:
  PROBLEM 1: HTTPBearer(auto_error=True) is the default. When the Authorization
             header is missing entirely, FastAPI raises a 403 "Not authenticated"
             with a plain-string body — not the JSON 401 your frontend expects.
             Setting auto_error=False lets us raise our own 401 with a proper
             JSON detail body.

  PROBLEM 2: The 401 on POST /documents/upload most likely means the frontend
             is sending the token in the wrong header format OR the token has
             already expired. This file adds explicit logging so you can see
             exactly which branch is failing.

  PROBLEM 3: payload.get("sub") returns a string (JWTs store 'sub' as string).
             Comparing it with int() was fine but int(user_id) would raise if
             sub was ever set to something non-numeric. Added explicit guard.

HOW TO SEND THE TOKEN FROM YOUR FRONTEND:
  Every protected request must include:
    Header: Authorization: Bearer <your_access_token>

  Example (fetch):
    fetch("/api/v1/documents/upload", {
      method: "POST",
      headers: { "Authorization": `Bearer ${token}` },
      body: formData,
    })

  Example (axios):
    axios.post("/api/v1/documents/upload", formData, {
      headers: { Authorization: `Bearer ${token}` }
    })
"""

import logging
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from core.security import decode_token
from db.database import get_db
from model.user import User

logger = logging.getLogger(__name__)

# auto_error=False → we control the 401 response body (JSON, not plain string)
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency — extracts and validates the Bearer token.
    Raises HTTP 401 with a JSON body on any auth failure.
    Inject with: current_user: User = Depends(get_current_user)
    """

    # ── 1. Check header was present ───────────────────────────────────────────
    if credentials is None:
        logger.warning("[Auth] Request missing Authorization header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing. Send: Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ── 2. Decode and verify JWT ──────────────────────────────────────────────
    token   = credentials.credentials
    payload = decode_token(token)

    if payload is None:
        logger.warning("[Auth] Token decode failed (expired or tampered)")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is invalid or has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ── 3. Extract user_id from 'sub' claim ───────────────────────────────────
    sub = payload.get("sub")
    if sub is None:
        logger.warning("[Auth] JWT missing 'sub' claim")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token: missing subject claim",
        )

    try:
        user_id = int(sub)
    except (ValueError, TypeError):
        logger.warning(f"[Auth] JWT 'sub' is not a valid integer: {sub!r}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token: subject must be a user ID",
        )

    # ── 4. Load user from DB ──────────────────────────────────────────────────
    user = db.query(User).filter(User.id == user_id).first()

    if user is None:
        logger.warning(f"[Auth] User ID {user_id} not found in DB")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found",
        )

    if not user.is_active:
        logger.warning(f"[Auth] User ID {user_id} is inactive")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been disabled. Contact support.",
        )

    return user