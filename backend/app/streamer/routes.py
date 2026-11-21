"""Streamer Mode (STREAMER_MODE.md): a streamer's profile and their voice, recorded once with consent.

A session started for a streamer (`POST /api/live/sessions` with `streamer_id`) speaks in this voice from its
first phrase. Sessions without a streamer use stock voices.
"""
import io
import re
import time
from typing import Annotated, Any

import numpy as np
import soundfile as sf
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.config import LANG_NAMES
from app.db import get_store
from app.live.pipeline import GPU_CHECK_LINES
from app.providers import get_gpu_voice, get_tts
from app.providers.base import ProviderError
from app.shared import voices
from app.streamer import voice_ref

router = APIRouter()
HANDLE = re.compile(r"^[a-z0-9_]{3,24}$")
VOICE_PUBLIC = ("ref_score", "ref_seconds", "ref_cleaned", "ref_cuts_tried", "ref_build_s")


class NewStreamer(BaseModel):
    handle: str
    display_name: str = Field(min_length=1, max_length=60)
    youtube_channel: str = ""
    default_langs: list[str] = Field(default_factory=lambda: ["ta-IN"], max_length=4)
    src_lang: str = "hi-IN"


async def get_streamer(sid: str) -> dict[str, Any]:
    store = get_store()
    row = await store.get("streamers", sid)
    if not row:
        found = await store.select("streamers", handle=sid.lower().lstrip("@"))
        row = found[0] if found else None
    if not row:
        raise HTTPException(404, "streamer not found")
    return row


async def public(row: dict[str, Any]) -> dict[str, Any]:
    out = {k: row.get(k) for k in ("id", "handle", "display_name", "youtube_channel", "default_langs", "src_lang",
                                   "created_at")}
    voice = await get_store().get("voice_profiles", row["voice_profile_id"]) if row.get("voice_profile_id") else None
    if voice and not voice.get("deleted_at") and voice.get("consent_at"):
        out["voice"] = {"id": voice["id"], "consent_at": voice["consent_at"], "gnani_clone": bool(voice.get("embedding")),
                        "gpu_voice": bool(voice.get("ref_path")), **{k: voice.get(k) for k in VOICE_PUBLIC}}
    else:
        out["voice"] = None
    return out


@router.get("/api/streamers/health")
async def health() -> dict[str, Any]:
    """What a streamer needs before going live. Engine times are measured by this call."""
    from app.config import get_settings
    s, gpu, engines = get_settings(), get_gpu_voice(), []
    if gpu.enabled:
        engines = [{"ok": bool(h.get("ok")), "ms": h.get("ms")} for h in await gpu.health()]
    return {"gnani": bool(s.gnani_api_key.get_secret_value()) or s.mock_providers,
            "llm": bool(s.llm_base_url and s.llm_model) or s.mock_providers,
            "gpu_engines": engines, "gpu_separate": bool(s.gpu_separate_url)}


@router.post("/api/streamers", status_code=201)
async def create_streamer(body: NewStreamer) -> dict[str, Any]:
    handle = body.handle.strip().lower().lstrip("@")
    if not HANDLE.match(handle):
        raise HTTPException(400, "Handle: 3 to 24 letters, digits or underscores.")
    bad = [lg for lg in body.default_langs if lg not in LANG_NAMES]
    if bad or (body.src_lang != "indic-auto" and body.src_lang not in LANG_NAMES):
        raise HTTPException(400, f"unsupported language: {bad or body.src_lang}")
    store = get_store()
    if await store.select("streamers", handle=handle):
        raise HTTPException(409, "That handle is taken.")
    row = await store.insert("streamers", {
        "handle": handle, "display_name": body.display_name.strip(), "youtube_channel": body.youtube_channel.strip()[:120],
        "default_langs": list(dict.fromkeys(body.default_langs)), "src_lang": body.src_lang, "voice_profile_id": None})
    return await public(row)


@router.get("/api/streamers/{sid}")
async def read_streamer(sid: str) -> dict[str, Any]:
    return await public(await get_streamer(sid))


class EditStreamer(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=60)
    youtube_channel: str | None = None
    default_langs: list[str] | None = Field(default=None, min_length=1, max_length=4)


@router.patch("/api/streamers/{sid}")
async def edit_streamer(sid: str, body: EditStreamer) -> dict[str, Any]:
    """Name, channel and languages. The handle stays, and so does a recorded voice (its consent was the speaker's)."""
    s = await get_streamer(sid)
    fields: dict[str, Any] = {}
    if body.display_name is not None:
        if not body.display_name.strip():
            raise HTTPException(400, "A name is needed.")
        fields["display_name"] = body.display_name.strip()
    if body.youtube_channel is not None:
        fields["youtube_channel"] = body.youtube_channel.strip()[:120]
    if body.default_langs is not None:
        bad = [lg for lg in body.default_langs if lg not in LANG_NAMES]
        if bad:
            raise HTTPException(400, f"unsupported language: {bad}")
        fields["default_langs"] = list(dict.fromkeys(body.default_langs))
    if fields:
        s = await get_store().update("streamers", s["id"], fields) or s
    return await public(s)


@router.delete("/api/streamers/{sid}")
async def delete_streamer(sid: str) -> dict[str, bool]:
    """The profile and, with it, the recorded voice and its copies. The handle becomes free again."""
    s = await get_streamer(sid)
    if s.get("voice_profile_id"):
        await _drop_voice(s["voice_profile_id"])
    await get_store().delete("streamers", id=s["id"])
    return {"deleted": True}


@router.post("/api/streamers/{sid}/voice", status_code=201)
async def record_voice(
    sid: str,
    sample: Annotated[UploadFile, File()],
    consent_text: Annotated[str, Form()],
    consent: Annotated[bool, Form()] = False,
) -> dict[str, Any]:
    """The streamer's own recording (20-30 s, consent sentence read aloud) -> Gnani clone + scored GPU voice."""
    s = await get_streamer(sid)
    # Consent is checked (403) and the Gnani embedding made by the same code as /api/voices.
    v = await voices.create_voice(sample=sample, consent_text=consent_text, consent=consent,
                                  display_name=f"{s['display_name']} (streamer)")
    store = get_store()
    profile = await store.get("voice_profiles", v["id"])
    assert profile is not None
    check_lang = next((lg for lg in s["default_langs"] if lg in GPU_CHECK_LINES), "ta-IN")
    try:
        ref = await voice_ref.build(profile["id"], voices.voices_dir() / profile["sample_path"],
                                    consent_at=profile["consent_at"], src_lang=s.get("src_lang") or "hi-IN",
                                    check_lang=check_lang, out_dir=voices.voices_dir())
    except Exception:  # noqa: BLE001 - the Gnani clone still works; the GPU voice can be rebuilt later
        ref = None
    if ref:
        await store.update("voice_profiles", profile["id"], ref)
    if s.get("voice_profile_id") and s["voice_profile_id"] != profile["id"]:
        await _drop_voice(s["voice_profile_id"])
    s = await store.update("streamers", s["id"], {"voice_profile_id": profile["id"]}) or s
    return await public(s)


async def _drop_voice(profile_id: str) -> None:
    p = await get_store().get("voice_profiles", profile_id)
    if p and not p.get("deleted_at"):
        if p.get("ref_path"):
            (voices.voices_dir() / p["ref_path"]).unlink(missing_ok=True)
        await voices.delete_voice(profile_id)
        await get_store().update("voice_profiles", profile_id, {"ref_path": None, "ref_text": None})


@router.delete("/api/streamers/{sid}/voice")
async def delete_voice(sid: str) -> dict[str, bool]:
    s = await get_streamer(sid)
    if not s.get("voice_profile_id"):
        raise HTTPException(404, "no voice recorded")
    await _drop_voice(s["voice_profile_id"])
    await get_store().update("streamers", s["id"], {"voice_profile_id": None})
    return {"deleted": True}


@router.post("/api/streamers/{sid}/voice/preview")
async def preview_voice(sid: str, lang: str = "ta-IN") -> Response:
    """One known sentence in the streamer's voice, as WAV. Headers say which engine made it and how long it took."""
    s = await get_streamer(sid)
    p = await get_store().get("voice_profiles", s.get("voice_profile_id") or "")
    if not p or p.get("deleted_at") or not p.get("consent_at"):
        raise HTTPException(403, "Record your voice with consent first.")
    line = GPU_CHECK_LINES.get(lang)
    if not line:
        raise HTTPException(400, f"no preview line for {lang}")
    gpu, t0 = get_gpu_voice(), time.perf_counter()
    try:
        if p.get("ref_path") and gpu.speaks(lang):
            vid = voice_ref.engine_voice_id(p["id"])
            path = voices.voices_dir() / p["ref_path"]
            text = await voice_ref.sample_text(p, path, s.get("src_lang") or "hi-IN")
            await gpu.set_ref(vid, str(path), text, consent_at=p["consent_at"])
            pcm, rate = await gpu.synth(vid, line, lang)
            buf = io.BytesIO()
            sf.write(buf, np.frombuffer(pcm, dtype="<i2"), rate, format="WAV", subtype="PCM_16")
            wav, engine = buf.getvalue(), "gpu"
        elif p.get("embedding"):
            wav, engine = await get_tts().synth(line, lang, {"kind": "clone", "embedding": p["embedding"]}), "gnani"
        else:
            raise HTTPException(409, "This voice has no copy to speak with.")
    except ProviderError as e:
        raise HTTPException(502, f"Preview failed: {e}") from e
    return Response(content=wav, media_type="audio/wav", headers={
        "X-Engine": engine, "X-Preview-Ms": f"{(time.perf_counter() - t0) * 1000:.0f}",
        "Access-Control-Expose-Headers": "X-Engine, X-Preview-Ms"})
