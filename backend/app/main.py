"""FastAPI entrypoint. Run: uvicorn app.main:app --reload (from backend/)."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings

settings = get_settings()
app = FastAPI(title="Bharat Dub API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, object]:
    """Liveness plus which integrations are configured (booleans only, never values)."""
    return {
        "ok": True,
        "configured": {
            "gnani": bool(settings.gnani_api_key.get_secret_value()),
            "llm": bool(settings.llm_base_url and settings.llm_model),
            "supabase": bool(settings.supabase_url and settings.supabase_service_key.get_secret_value()),
        },
    }
