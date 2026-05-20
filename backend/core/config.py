from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    DB_SERVER: str
    DATABASE: str
    DB_USER: str
    DB_PASSWORD: str
    DB_DRIVER: str = "ODBC Driver 17 for SQL Server"

    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # App
    APP_NAME: str = "Document Assistant"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    DEBUG: bool = False

    # Ollama
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_EMBED_MODEL: str = "mxbai-embed-large"
    OLLAMA_LLM_MODEL: str = "mistral"

    # CORS
    FRONTEND_URL: str = "http://localhost:5173"
    CORS_ORIGINS: str = ""          # optional comma-separated list

    @property
    def DATABASE_URL(self) -> str:
        import urllib.parse
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
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",          # ignore unknown .env keys
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()