"""Live session state and lifecycle. One LivePipeline per running session, kept in memory."""
import asyncio
import re
import secrets
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from app.db import get_store
from app.live.bus import Bus
from app.v1 import record

YT_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
YT_URL = re.compile(r"(?:v=|youtu\.be/|/live/|/embed/|/shorts/)([A-Za-z0-9_-]{11})")


def parse_youtube_id(raw: str) -> str | None:
    raw = raw.strip()
    if YT_ID.match(raw):
        return raw
    m = YT_URL.search(raw)
    return m.group(1) if m else None


@dataclass
class LiveSession:
    row: dict[str, Any]
    bus: Bus = field(default_factory=Bus)
    t0: float = field(default_factory=time.monotonic)
    latencies: dict[str, deque[int]] = field(default_factory=dict)
    heard: dict[str, deque[int]] = field(default_factory=dict)
    chunk_count: int = 0
    pipeline: Any = None
    prefetch: Any = None   # v1.1 warm start: a streamer's stored voice on its way to the engines

    @property
    def id(self) -> str:
        return str(self.row["id"])

    @property
    def langs(self) -> list[str]:
        return list(self.row["target_langs"])

    def now_ms(self) -> int:
        return int((time.monotonic() - self.t0) * 1000)

    def record_latency(self, lang: str, ms: int) -> None:
        self.latencies.setdefault(lang, deque(maxlen=500)).append(ms)

    def record_heard(self, lang: str, ms: int) -> None:
        """End of a phrase to the moment a viewer starts hearing its dub (after earlier phrases have played)."""
        self.heard.setdefault(lang, deque(maxlen=500)).append(ms)

    def public(self) -> dict[str, Any]:
        r = self.row
        rec = {"recording": True} if record.wanted(r) else {}   # v1.1: only on a session that asked to be kept
        return {**rec, "id": self.id, "youtube_video_id": r.get("youtube_video_id"), "target_langs": self.langs,
                "src_lang": r.get("src_lang") or "indic-auto", "offset_ms": r.get("offset_ms") or 0,
                "status": r.get("status") or "idle", "created_at": r.get("created_at"),
                "voice_profile_id": r.get("voice_profile_id"), "viewers": self.bus.viewer_count(),
                "voice_from_stream": bool((r.get("voice_from_stream") or {}).get("consent_at")),
                "clone_langs": list(self.pipeline.clone_langs) if self.pipeline else None,
                "sync_delay_ms": self.pipeline.sync_delay() if self.pipeline else 0,
                "gpu_voice": bool(self.pipeline and self.pipeline.gpu_ready),
                "streamer_id": r.get("streamer_id"), "voice_mode": r.get("voice_mode"),
                "engine": r.get("engine") or "cloud",
                "gpu_voice_score": self.pipeline._gpu_score if self.pipeline else None}


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, LiveSession] = {}
        self._lock = asyncio.Lock()

    async def create(self, youtube_video_id: str | None, target_langs: list[str], voice_profile_id: str | None,
                     offset_ms: int = 0, voice_from_stream: dict[str, str] | None = None,
                     src_lang: str = "indic-auto") -> tuple[LiveSession, str]:
        token = secrets.token_urlsafe(18)
        row = await get_store().insert("live_sessions", {
            "youtube_video_id": youtube_video_id, "target_langs": target_langs,
            "voice_profile_id": voice_profile_id, "offset_ms": offset_ms, "status": "idle",
            "ingest_token": token, "voice_from_stream": voice_from_stream, "src_lang": src_lang,
        })
        sess = LiveSession(row)
        self._sessions[sess.id] = sess
        return sess, token

    async def get(self, sid: str) -> LiveSession | None:
        if sid in self._sessions:
            return self._sessions[sid]
        async with self._lock:
            if sid in self._sessions:
                return self._sessions[sid]
            try:
                row = await get_store().get("live_sessions", sid)
            except Exception:  # noqa: BLE001 - bad uuid etc.
                return None
            if not row:
                return None
            sess = LiveSession(row)
            self._sessions[sid] = sess
            return sess

    async def update(self, sess: LiveSession, **fields: Any) -> None:
        sess.row.update(fields)
        await get_store().update("live_sessions", sess.id, fields)


sessions = SessionManager()
