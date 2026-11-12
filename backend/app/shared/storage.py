"""Output files: Supabase Storage when configured, else served locally from /files/{job_id}/{name}."""
import asyncio
import mimetypes
from pathlib import Path

from app.config import get_settings

SIGNED_URL_TTL_S = 3600


async def publish_output(job_id: str, path: Path) -> str:
    """Upload a render output if Supabase is configured; return the stored path (bucket key or local name)."""
    s = get_settings()
    if not s.use_supabase:
        return path.name
    from app.db import SupabaseStore, get_store

    store = get_store()
    assert isinstance(store, SupabaseStore)
    key = f"{job_id}/{path.name}"
    data = path.read_bytes()
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    await asyncio.to_thread(lambda: store.client.storage.from_("renders").upload(
        key, data, {"content-type": ctype, "upsert": "true"}))
    return key


async def output_url(job_id: str, stored: str) -> str:
    s = get_settings()
    if not s.use_supabase:
        return f"{s.public_api_base.rstrip('/')}/files/{job_id}/{stored}"
    from app.db import SupabaseStore, get_store

    store = get_store()
    assert isinstance(store, SupabaseStore)
    res = await asyncio.to_thread(lambda: store.client.storage.from_("renders").create_signed_url(
        stored, SIGNED_URL_TTL_S))
    return res.get("signedURL") or res.get("signedUrl") or ""
