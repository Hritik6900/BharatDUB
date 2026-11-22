"""Live REST + WebSockets (SPEC.md section 11)."""
import asyncio
import contextlib
import json
import secrets
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.config import LANG_NAMES, get_settings
from app.db import get_store, now_iso
from app.live.bus import ALL
from app.live.chat import chat
from app.live.pipeline import LivePipeline
from app.live.session import LiveSession, parse_youtube_id, sessions
from app.shared.metrics import percentile

router = APIRouter()
# A streamer's own mic is real time while YouTube shows it 5-30 s later: the dub waits that long (the offset).
MAX_OFFSET_MS = 40000
# Shown next to the checkbox on /live; stored on the voice profile the stream creates.
STREAM_VOICE_CONSENT = ("The voice on this stream is mine, or I have the speaker's permission, and I agree that "
                        "Bharat Dub may make a copy of it to dub this stream.")


class CreateSession(BaseModel):
    youtube_video_id: str = ""
    target_langs: list[str] = Field(min_length=1, max_length=4)
    voice_profile_id: str | None = None
    voice_from_stream: bool = False   # learn the speaker's voice from the first seconds of the stream
    voice_consent: bool = False
    src_lang: str = "hi-IN"            # language the streamer speaks; `indic-auto` to detect
    streamer_id: str | None = None     # Streamer Mode: the session belongs to this streamer
    voice_mode: str = "clone"          # with a streamer: `clone` = their recorded voice, `stock` = never clone
    offset_ms: int = 0
    engine: str = "cloud"              # `gpu` = speech-to-text and translation on our own GPU machine (when set up)
    glossary: list[str] = Field(default_factory=list, max_length=100)   # words kept as they are, this session only


class PatchSession(BaseModel):
    offset_ms: int | None = None
    youtube_video_id: str | None = None


async def _sess(sid: str) -> LiveSession:
    s = await sessions.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    return s


@router.post("/api/live/sessions", status_code=201)
async def create_session(body: CreateSession) -> dict[str, Any]:
    bad = [lg for lg in body.target_langs if lg not in LANG_NAMES or lg == "hi-IN"]
    if bad:
        raise HTTPException(400, f"unsupported target languages: {bad}")
    if body.src_lang != "indic-auto" and body.src_lang not in LANG_NAMES:
        raise HTTPException(400, f"unsupported source language: {body.src_lang}")
    if body.engine not in ("cloud", "gpu"):
        raise HTTPException(400, "engine is cloud or gpu")
    if body.engine == "gpu" and not get_settings().gpu_mode_ready:
        raise HTTPException(400, "The GPU engine is not set up on this server.")
    yt = parse_youtube_id(body.youtube_video_id) if body.youtube_video_id else None
    if body.youtube_video_id and not yt:
        raise HTTPException(400, "Could not read a YouTube video id from that link.")
    streamer = None
    if body.streamer_id:
        streamer = await get_store().get("streamers", body.streamer_id)
        if not streamer:
            raise HTTPException(404, "streamer not found")
        if body.voice_mode not in ("clone", "stock"):
            raise HTTPException(400, "voice_mode is clone or stock")
        # The streamer's own recorded voice (consent was taken when it was recorded), or none at all.
        body.voice_profile_id = streamer.get("voice_profile_id") if body.voice_mode == "clone" else None
        body.voice_from_stream = False
        if body.voice_mode == "clone" and not body.voice_profile_id:
            raise HTTPException(403, "Record your voice with consent before going live in your own voice.")
    if not streamer and get_settings().v1_live_stock_default:
        # v1: a stream without a streamer profile (someone else's content) is dubbed in stock voices. A copied
        # voice is only for a streamer who recorded their own with consent.
        body.voice_from_stream, body.voice_profile_id = False, None
    if not streamer and get_settings().live_clone_needs_streamer and (body.voice_from_stream or body.voice_profile_id):
        raise HTTPException(403, "A copied voice needs a streamer profile with the speaker's own recorded consent. "
                                 "This session can use stock voices; to go live in your own voice, record it on /streamer.")
    if body.voice_profile_id:
        p = await get_store().get("voice_profiles", body.voice_profile_id)
        if not p or not p.get("consent_at") or p.get("deleted_at"):
            raise HTTPException(403, "This voice profile has no recorded consent.")
    if body.voice_from_stream and not body.voice_consent:
        raise HTTPException(403, "Copying the voice on this stream needs the speaker's consent.")
    from_stream = None
    if body.voice_from_stream and not body.voice_profile_id:
        from_stream = {"consent_at": now_iso(), "consent_text": STREAM_VOICE_CONSENT}
    sess, token = await sessions.create(yt, list(dict.fromkeys(body.target_langs)), body.voice_profile_id,
                                        max(-5000, min(MAX_OFFSET_MS, body.offset_ms)), from_stream, body.src_lang)
    if streamer:
        await sessions.update(sess, streamer_id=streamer["id"], voice_mode=body.voice_mode)
    if body.engine == "gpu":   # stored only when chosen: a session without it is the hosted path, untouched
        await sessions.update(sess, engine="gpu")
    terms = list(dict.fromkeys(t.strip()[:60] for t in body.glossary if t.strip()))
    if terms:
        await sessions.update(sess, glossary=terms)
    return {"session_id": sess.id, "ingest_token": token, **sess.public()}


@router.get("/api/live/sessions")
async def list_sessions() -> list[dict[str, Any]]:
    rows = await get_store().select("live_sessions", order="created_at", desc=True, limit=20)
    out = []
    for r in rows:
        s = await sessions.get(str(r["id"]))
        if s:
            out.append(s.public())
    return out


@router.get("/api/live/sessions/{sid}")
async def get_session(sid: str) -> dict[str, Any]:
    s = await _sess(sid)
    return {**s.public(), "stats": s.pipeline.stats() if s.pipeline else None}


@router.patch("/api/live/sessions/{sid}")
async def patch_session(sid: str, body: PatchSession) -> dict[str, Any]:
    s = await _sess(sid)
    fields: dict[str, Any] = {}
    if body.offset_ms is not None:
        fields["offset_ms"] = max(-5000, min(MAX_OFFSET_MS, body.offset_ms))
    if body.youtube_video_id is not None:
        yt = parse_youtube_id(body.youtube_video_id)
        if not yt:
            raise HTTPException(400, "Could not read a YouTube video id from that link.")
        fields["youtube_video_id"] = yt
    if fields:
        await sessions.update(s, **fields)
        s.bus.broadcast({"type": "session", **s.public()})
    return s.public()


async def start_pipeline(s: LiveSession) -> None:
    if s.pipeline and s.pipeline.running:
        return
    s.pipeline = LivePipeline(s)
    await s.pipeline.start()
    await sessions.update(s, status="live")
    s.bus.broadcast({"type": "session", **s.public()})


@router.post("/api/live/sessions/{sid}/start")
async def start_session(sid: str) -> dict[str, Any]:
    s = await _sess(sid)
    await start_pipeline(s)
    return s.public()


@router.post("/api/live/sessions/{sid}/stop")
async def stop_session(sid: str) -> dict[str, Any]:
    s = await _sess(sid)
    if s.pipeline:
        await s.pipeline.stop()
    await sessions.update(s, status="ended")
    s.bus.broadcast({"type": "session", **s.public()})
    return s.public()


@router.get("/api/live/sessions/{sid}/metrics")
async def session_metrics(sid: str) -> dict[str, Any]:
    s = await _sess(sid)
    per_lang = {}
    for lang, vals in s.latencies.items():
        v = list(vals)
        h = list(s.heard.get(lang, ()))
        per_lang[lang] = {"p50_ms": percentile(v, 50), "p95_ms": percentile(v, 95), "n": len(v),
                          "recent_ms": v[-60:], "heard_p50_ms": percentile(h, 50), "heard_p95_ms": percentile(h, 95)}
    all_ms = [x for d in s.latencies.values() for x in d]
    heard = [x for d in s.heard.values() for x in d]
    return {"chunks": s.chunk_count, "p50_ms": percentile(all_ms, 50), "p95_ms": percentile(all_ms, 95),
            "n": len(all_ms), "heard_p50_ms": percentile(heard, 50), "heard_p95_ms": percentile(heard, 95),
            "per_lang": per_lang, **(s.pipeline.sync_stats() if s.pipeline else {})}


# ---------- WebSockets ----------
@router.websocket("/ws/ingest/{sid}")
async def ws_ingest(ws: WebSocket, sid: str, token: str = Query("")) -> None:
    s = await sessions.get(sid)
    expected = (s.row.get("ingest_token") or "") if s else ""
    if not s or not expected or not secrets.compare_digest(token, expected):
        await ws.close(code=4403)
        return
    await ws.accept()
    await start_pipeline(s)
    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            if msg.get("bytes") and s.pipeline:
                s.pipeline.feed(msg["bytes"])
            elif msg.get("text") and s.pipeline:
                # The console says where the video it is feeding from is: {"type":"media","t":<s>,"playing":bool}
                with contextlib.suppress(ValueError, TypeError):
                    data = json.loads(msg["text"])
                    if data.get("type") == "media":
                        s.pipeline.set_media(float(data["t"]), bool(data.get("playing", True)))
    except WebSocketDisconnect:
        pass


async def _pump(ws: WebSocket, q: asyncio.Queue[dict[str, Any]]) -> None:
    while True:
        await ws.send_text(json.dumps(await q.get(), ensure_ascii=False))


@router.websocket("/ws/watch/{sid}")
async def ws_watch(ws: WebSocket, sid: str, lang: str = Query("ta-IN")) -> None:
    s = await sessions.get(sid)
    if not s:
        await ws.close(code=4404)
        return
    if lang not in s.langs and lang not in ("src", ALL):
        await ws.close(code=4400)
        return
    await ws.accept()
    q = s.bus.subscribe(lang)
    try:
        await ws.send_text(json.dumps({"type": "hello", "session": s.public(),
                                       "stats": s.pipeline.stats() if s.pipeline else None}))
        langs = [lang] if lang != ALL else ["src", *s.langs]
        for lg in langs:
            for m in list(s.bus.history.get(lg, ())):
                await ws.send_text(json.dumps({**m, "history": True}, ensure_ascii=False))
        pump = asyncio.create_task(_pump(ws, q))
        try:
            while True:
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect":
                    break
                # A viewer reports how late each phrase really started for them: {"type":"played","late_ms":n}
                if msg.get("text") and s.pipeline:
                    with contextlib.suppress(ValueError, TypeError, KeyError):
                        data = json.loads(msg["text"])
                        if data.get("type") == "played":
                            seq = data.get("seq")
                            s.pipeline.viewer_played(lang, int(data["late_ms"]), int(seq) if isinstance(seq, int) else None)
        finally:
            pump.cancel()
    except WebSocketDisconnect:
        pass
    finally:
        s.bus.unsubscribe(lang, q)


@router.websocket("/ws/chat/{sid}")
async def ws_chat(ws: WebSocket, sid: str, lang: str = Query("en-IN"), name: str = Query("")) -> None:
    s = await sessions.get(sid)
    if not s:
        await ws.close(code=4404)
        return
    await ws.accept()
    q = chat.subscribe(sid)
    last = 0.0
    try:
        for m in list(chat.history.get(sid, ())):
            await ws.send_text(json.dumps(m, ensure_ascii=False))
        pump = asyncio.create_task(_pump(ws, q))
        try:
            while True:
                raw = await ws.receive_text()
                with contextlib.suppress(ValueError):
                    data = json.loads(raw)
                    text = str(data.get("text", "")).strip()
                    if text and time.monotonic() - last >= 1.0:
                        last = time.monotonic()
                        await chat.post(sid, str(data.get("lang") or lang)[:8], text, str(data.get("name") or name))
        finally:
            pump.cancel()
    except WebSocketDisconnect:
        pass
    finally:
        chat.unsubscribe(sid, q)
