"""
security.py — Password hashing + JWT
======================================
FIX APPLIED:
  PROBLEM: passlib 1.7.4 reads bcrypt.__about__.__version__ at import time.
           bcrypt 4.x removed the __about__ module → AttributeError on startup.
           The error is non-fatal (passlib catches it internally) BUT it means
           passlib cannot detect the bcrypt version, so it falls back to a slower
           pure-python path and logs a noisy warning on every startup.

  ROOT CAUSE: passlib has not been updated for bcrypt >= 4.0.

  SOLUTION: Bypass passlib entirely for bcrypt. Call bcrypt directly.
            bcrypt 4.x API: bcrypt.hashpw() / bcrypt.checkpw() — stable since 3.x.
            This removes the passlib dependency for password hashing completely.

  JWT (python-jose) is unchanged — it works correctly with your current deps.

  ALSO FIXED: added auto_error=False to HTTPBearer in deps.py so that the
  401 on /documents/upload returns a proper JSON error body instead of
  FastAPI's generic "Not authenticated" string.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt

from core.config import settings


# ── Password hashing (direct bcrypt — no passlib) ─────────────────────────────

def hash_password(password: str) -> str:
    """
    Hash a plain-text password.
    bcrypt.hashpw requires bytes; returns bytes → decode to str for DB storage.
    Cost factor (rounds) defaults to 12 in bcrypt 4.x — fine for auth.
    """
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """
    Verify a plain-text password against a stored bcrypt hash.
    Both inputs converted to bytes before comparison.
    Returns False (not raises) if the hash is malformed — safe for login flow.
    """
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ── JWT ────────────────────────────────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a signed JWT.
    Payload 'sub' should be the user ID as a string.
    Expiry defaults to settings.ACCESS_TOKEN_EXPIRE_MINUTES (60 min).
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """
    Decode and verify a JWT.
    Returns the payload dict on success, None on any failure (expired, tampered, etc.).
    Callers should treat None as 401.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        return payload
    except JWTError:
        return None