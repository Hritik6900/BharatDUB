"""FastAPI entrypoint. Run: uvicorn app.main:app --reload (from backend/)."""
import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import get_store
from app.live import routes as live_routes
from app.shared import dashboard, glossary, voices
from app.streamer import routes as streamer_routes
from app.studio import routes as studio_routes

log = logging.getLogger("app")
settings = get_settings()


async def sweep_expired_uploads() -> int:
    """Delete local job files past expires_at (uploads auto-deleted after UPLOAD_TTL_HOURS)."""
    store, now, n = get_store(), datetime.now(timezone.utc), 0
    for job in await store.select("jobs"):
        exp = job.get("expires_at")
        if exp and job.get("status") != "expired" and datetime.fromisoformat(str(exp)) < now:
            studio_routes.delete_job_files(job["id"])
            await store.update("jobs", job["id"], {"status": "expired"})
            n += 1
    return n


async def _sweeper() -> None:
    while True:
        with suppress(Exception):
            await sweep_expired_uploads()
        await asyncio.sleep(1800)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(_sweeper())
    yield
    task.cancel()


app = FastAPI(title="Bharat Dub API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(studio_routes.router)
app.include_router(voices.router)
app.include_router(glossary.router)
app.include_router(live_routes.router)
app.include_router(dashboard.router)
app.include_router(streamer_routes.router)


@app.get("/health")
async def health() -> dict[str, object]:
    """Liveness plus which integrations are configured (booleans only, never values)."""
    return {
        "ok": True,
        "configured": {
            "gnani": bool(settings.gnani_api_key.get_secret_value()),
            "llm": bool(settings.llm_base_url and settings.llm_model),
            "supabase": settings.use_supabase,
        },
        "mock_providers": settings.mock_providers,
    }
