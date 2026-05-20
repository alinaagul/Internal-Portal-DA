from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,       # verify connection is alive before using
    pool_size=5,
    max_overflow=10,
    echo=settings.DEBUG,      # log SQL in debug mode
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency — yields a DB session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_connection() -> bool:
    """Ping the database — called at startup."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        print(f"[DB] Connection failed: {e}")
        return False
