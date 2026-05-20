from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from core.config import settings
from db.database import Base, engine, test_connection
from model import user  
from routers import auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    print(f"\n{'='*50}")
    print(f"  {settings.APP_NAME} — Backend")
    print(f"{'='*50}")

    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)
    print("[DB] Tables verified/created ✓")

    # Test SQL Server connection
    if test_connection():
        print(f"[DB] Connected to {settings.DB_SERVER}/{settings.DATABASE} ✓")
    else:
        print("[DB] ⚠ Could not reach SQL Server — check .env credentials")

    print(f"[App] Running at http://{settings.APP_HOST}:{settings.APP_PORT}")
    print(f"[Docs] Swagger UI → http://{settings.APP_HOST}:{settings.APP_PORT}/docs\n")
    yield
    # ── Shutdown ──
    print("[App] Shutting down...")


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="Document Assistant — Auth + RAG API",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.DEBUG,
    )
