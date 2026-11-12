"""Live REST + WebSockets (SPEC.md section 11)."""
import asyncio
import contextlib
import json
import secrets
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.config import LANG_NAMES
from app.db import get_store
from app.live.bus import ALL
from app.live.chat import chat
from app.live.pipeline import LivePipeline
from app.live.session import LiveSession, parse_youtube_id, sessions
from app.shared.metrics import percentile

router = APIRouter()


class CreateSession(BaseModel):
    youtube_video_id: str = ""
    target_langs: list[str] = Field(min_length=1, max_length=4)
    voice_profile_id: str | None = None
    offset_ms: int = 0


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
    yt = parse_youtube_id(body.youtube_video_id) if body.youtube_video_id else None
    if body.youtube_video_id and not yt:
        raise HTTPException(400, "Could not read a YouTube video id from that link.")
    if body.voice_profile_id:
        p = await get_store().get("voice_profiles", body.voice_profile_id)
        if not p or not p.get("consent_at") or p.get("deleted_at"):
            raise HTTPException(403, "This voice profile has no recorded consent.")
    sess, token = await sessions.create(yt, list(dict.fromkeys(body.target_langs)), body.voice_profile_id,
                                        max(-5000, min(10000, body.offset_ms)))
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
        fields["offset_ms"] = max(-5000, min(10000, body.offset_ms))
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
        per_lang[lang] = {"p50_ms": percentile(v, 50), "p95_ms": percentile(v, 95), "n": len(v),
                          "recent_ms": v[-60:]}
    all_ms = [x for d in s.latencies.values() for x in d]
    return {"chunks": s.chunk_count, "p50_ms": percentile(all_ms, 50), "p95_ms": percentile(all_ms, 95),
            "n": len(all_ms), "per_lang": per_lang}


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
                if (await ws.receive())["type"] == "websocket.disconnect":
                    break
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
