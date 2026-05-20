"""
celery_app/celery_config.py
============================
Celery app factory.
Broker  : Redis (local)  — queues tasks
Backend : Redis (local)  — stores task results + state

Install Redis on Windows:
  Option A (recommended): Use WSL2 → apt install redis-server
  Option B: Download from https://github.com/tporadowski/redis/releases
            Run redis-server.exe

Verify Redis is running:
  redis-cli ping  → should return PONG
"""

from celery import Celery
from core.config import settings

def make_celery() -> Celery:
    celery = Celery(
        "doc_assistant",
        broker=settings.REDIS_URL,
        backend=settings.REDIS_URL,
        include=["celery_app.tasks"],   # auto-discover tasks
    )

    celery.conf.update(
        # ── Serialization ─────────────────────────────────────────────────────
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],

        # ── Timeouts ──────────────────────────────────────────────────────────
        task_soft_time_limit=600,      # 10 min soft limit → raises SoftTimeLimitExceeded
        task_time_limit=720,           # 12 min hard kill
        task_acks_late=True,           # ack AFTER task completes (safe retry on crash)

        # ── Retries ───────────────────────────────────────────────────────────
        task_max_retries=3,
        task_default_retry_delay=10,   # seconds between retries

        # ── Result expiry ─────────────────────────────────────────────────────
        result_expires=86400,          # keep results for 24h

        # ── Worker ────────────────────────────────────────────────────────────
        worker_prefetch_multiplier=1,  # one task at a time per worker (heavy OCR)
        worker_max_tasks_per_child=10, # restart worker every 10 tasks (free memory)

        # ── Queues ────────────────────────────────────────────────────────────
        task_routes={
            "celery_app.tasks.process_document": {"queue": "documents"},
        },
        task_default_queue="documents",
    )

    return celery


celery_app = make_celery()