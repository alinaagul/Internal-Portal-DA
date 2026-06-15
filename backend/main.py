from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from core.config import settings
from db.database import Base, engine, test_connection
from model import user      # noqa
from model import document  # noqa
from model import chat       # noqa  ← registers chat_sessions + chat_messages
from routers import auth, documents
from routers import chat as chat_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"\n{'='*50}")
    print(f"  {settings.APP_NAME} — Backend")
    print(f"{'='*50}")
    try:
        Base.metadata.create_all(bind=engine)
        print(f"[DB] Connected to {settings.DB_SERVER}/{settings.DATABASE} ✓")
        print("[DB] Tables verified/created ✓")
    except Exception as e:
        print(f"[DB] ⚠ Could not connect: {e}")
        print("[DB] Server will start anyway — fix DB and restart")

    print(f"[App] Running at http://{settings.APP_HOST}:{settings.APP_PORT}")
    print(f"[Docs] Swagger UI → http://{settings.APP_HOST}:{settings.APP_PORT}/docs\n")
    yield
    print("[App] Shutting down...")


app = FastAPI(
    title=settings.APP_NAME,
    version="0.3.0",
    description="Document Assistant — Auth + OCR + RAG + Chat",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,        prefix="/api/v1")
app.include_router(documents.router,   prefix="/api/v1")
app.include_router(chat_router.router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME, "version": "0.3.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.APP_HOST, port=settings.APP_PORT, reload=settings.DEBUG)
