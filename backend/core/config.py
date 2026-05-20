"""
config.py — Application Settings
===================================
FIX APPLIED:
  PROBLEM: The bottom of your original config.py had stray module-level variable
           assignments after settings = get_settings():

             OLLAMA_BASE_URL      = "http://localhost:11434"
             OLLAMA_EMBED_MODEL   = "mxbai-embed-large"
             OLLAMA_CHAT_MODEL    = "mistral:7b-instruct"
             OLLAMA_CITATION_MODEL = "neural-chat"

           These are plain Python variables, NOT part of the Settings class.
           Any import that does `from core.config import OLLAMA_CHAT_MODEL`
           would get the hardcoded string instead of the .env value.
           Removed them — use settings.OLLAMA_CHAT_MODEL everywhere.

  ALSO ADDED:
    - OLLAMA_CHAT_MODEL and OLLAMA_CITATION_MODEL as proper Settings fields
      (were missing from original — chat_service.py references them)
    - get_all_origins() helper for CORS setup in main.py
"""

import urllib.parse
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    # ── Database (SQL Server via pyodbc) ──────────────────────────────────────
    DB_SERVER:   str
    DATABASE:    str
    DB_USER:     str
    DB_PASSWORD: str
    DB_DRIVER:   str = "ODBC Driver 17 for SQL Server"

    # ── JWT ───────────────────────────────────────────────────────────────────
    SECRET_KEY:                  str
    ALGORITHM:                   str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # ── App ───────────────────────────────────────────────────────────────────
    APP_NAME: str = "Document Assistant"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    DEBUG:    bool = False

    # ── Ollama ────────────────────────────────────────────────────────────────
    OLLAMA_BASE_URL:       str = "http://localhost:11434"
    OLLAMA_EMBED_MODEL:    str = "mxbai-embed-large"       # embeddings
    OLLAMA_CHAT_MODEL:     str = "mistral:7b-instruct"     # Q&A + summaries
    OLLAMA_CITATION_MODEL: str = "neural-chat"             # citation formatting
    # Legacy alias kept so existing code using OLLAMA_LLM_MODEL still works
    OLLAMA_LLM_MODEL:      str = "mistral:7b-instruct"

    # ── CORS ──────────────────────────────────────────────────────────────────
    FRONTEND_URL: str = "http://localhost:5173"
    CORS_ORIGINS: str = ""   # optional extra origins, comma-separated

    # ── Computed properties ───────────────────────────────────────────────────

    @property
    def DATABASE_URL(self) -> str:
        conn_str = (
            f"DRIVER={{{self.DB_DRIVER}}};"
            f"SERVER={self.DB_SERVER};"
            f"DATABASE={self.DATABASE};"
            f"UID={self.DB_USER};"
            f"PWD={self.DB_PASSWORD};"
            f"TrustServerCertificate=yes;"
            f"Encrypt=no;"
        )
        return "mssql+pyodbc:///?odbc_connect=" + urllib.parse.quote_plus(conn_str)

    def get_all_origins(self) -> List[str]:
        """
        Returns the full list of allowed CORS origins.
        Always includes FRONTEND_URL; adds any extras from CORS_ORIGINS.

        Use in main.py:
            from fastapi.middleware.cors import CORSMiddleware
            app.add_middleware(
                CORSMiddleware,
                allow_origins=settings.get_all_origins(),
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
        """
        origins = [self.FRONTEND_URL]
        if self.CORS_ORIGINS:
            extras = [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]
            origins.extend(extras)
        return origins

    model_config = {
        "env_file":          ".env",
        "env_file_encoding": "utf-8",
        "extra":             "ignore",   # silently ignore unknown .env keys
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()


# Single export — import this everywhere:
#   from core.config import settings
settings = get_settings()