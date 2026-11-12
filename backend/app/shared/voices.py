"""Voice profiles. Cloning only with recorded consent (golden rule 4); delete in one click."""
import asyncio
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.config import get_settings
from app.db import get_store, now_iso
from app.providers import get_tts
from app.providers.base import ProviderError
from app.shared import audio_utils as au

router = APIRouter()
PUBLIC = ("id", "display_name", "consent_text", "consent_at", "created_at")


def voices_dir() -> Path:
    d = get_settings().data_path / "voices"
    d.mkdir(exist_ok=True)
    return d


@router.post("/api/voices", status_code=201)
async def create_voice(
    sample: Annotated[UploadFile, File()],
    consent_text: Annotated[str, Form()],
    consent: Annotated[bool, Form()] = False,
    display_name: Annotated[str, Form()] = "My voice",
) -> dict[str, Any]:
    if not consent or not consent_text.strip():
        raise HTTPException(403, "Voice cloning needs the speaker's recorded consent.")
    vid = str(uuid.uuid4())
    raw = voices_dir() / f"{vid}_upload{Path(sample.filename or '.wav').suffix.lower() or '.wav'}"
    raw.write_bytes(await sample.read())
    wav = voices_dir() / f"{vid}.wav"
    try:
        await asyncio.to_thread(au.extract_wav, raw, wav, 44100)
        dur = au.duration_s(wav)
    except au.FFmpegError as e:
        raise HTTPException(400, "Could not read the audio sample.") from e
    finally:
        raw.unlink(missing_ok=True)
    if dur < 5:
        wav.unlink(missing_ok=True)
        raise HTTPException(400, f"Sample is {dur:.1f} s; record at least 5 s (20-30 s is best).")
    if dur > 30:
        audio = au.load_mono(wav)
        au.write_wav(wav, audio[: 30 * 44100])
    consent_at = now_iso()
    try:
        embedding = await get_tts().clone_embedding(str(wav), consent_at=consent_at)
    except ProviderError as e:
        wav.unlink(missing_ok=True)
        raise HTTPException(502, f"Voice cloning failed: {e}") from e
    row = await get_store().insert("voice_profiles", {
        "id": vid, "display_name": display_name.strip()[:60] or "My voice", "sample_path": wav.name,
        "embedding": embedding, "consent_text": consent_text.strip()[:2000], "consent_at": consent_at,
    })
    return {k: row.get(k) for k in PUBLIC}


@router.get("/api/voices")
async def list_voices() -> list[dict[str, Any]]:
    rows = await get_store().select("voice_profiles", order="created_at", desc=True)
    return [{k: r.get(k) for k in PUBLIC} for r in rows if not r.get("deleted_at")]


@router.delete("/api/voices/{vid}")
async def delete_voice(vid: str) -> dict[str, bool]:
    store = get_store()
    p = await store.get("voice_profiles", vid)
    if not p or p.get("deleted_at"):
        raise HTTPException(404, "voice profile not found")
    if p.get("sample_path"):
        (voices_dir() / Path(p["sample_path"]).name).unlink(missing_ok=True)
    await store.update("voice_profiles", vid, {"embedding": None, "sample_path": None, "deleted_at": now_iso()})
    return {"deleted": True}
