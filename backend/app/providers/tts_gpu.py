"""Our own GPU voice engine (IndicF5 on an A100, `voice_engine.py` on that machine): zero-shot voice cloning for Live.

It is not a Gnani model. It exists because a cloned line from Gnani takes 2-3.5 s and the account runs one request
at a time, so a copied voice could not keep up with a live speaker (measured 2026-11-14: 5 of 21 phrases).
Measured on the A100 the same day: 0.91 s for a ~2 s phrase, and no one-at-a-time limit.

Off unless `GPU_VOICE_URL` is set. The engine listens only on its own machine; reach it through an SSH tunnel.

  POST /ref   multipart: session_id, ref_text, audio  -> remembers the reference voice (3-10 s) for that session
  POST /tts   json {session_id, text, lang}           -> PCM16 mono at X-Sample-Rate (24 kHz)
"""
import time
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.providers.base import ProviderError
from app.providers.tts_gnani import ConsentRequired
from app.providers.http import request_with_retry

# IndicF5 speaks these; English is not among them (it stays on the Gnani voices).
GPU_LANGS = {"hi-IN", "ta-IN", "te-IN", "bn-IN", "kn-IN", "ml-IN", "mr-IN", "gu-IN", "pa-IN"}


class GpuVoice:
    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None) -> None:
        self.s = settings or get_settings()
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(self.s.gpu_voice_timeout_s, connect=3.0))
        self.last_synth_ms: float | None = None   # the engine's own time for the last line
        self.last_latency_s: float | None = None  # ... and the whole round trip

    @property
    def enabled(self) -> bool:
        return bool(self.s.gpu_voice_url)

    def speaks(self, lang: str) -> bool:
        return self.enabled and lang in GPU_LANGS

    def _url(self, path: str) -> str:
        return self.s.gpu_voice_url.rstrip("/") + path

    async def set_ref(self, session_id: str, wav_path: str, ref_text: str, *, consent_at: str | None) -> dict[str, Any]:
        """Give the engine the voice to copy: 3-10 s of speech and exactly what is said in it.
        Refuses without recorded consent (golden rule 4), like every other cloning call."""
        if not consent_at:
            raise ConsentRequired("voice cloning requires recorded consent", status=403)
        audio = Path(wav_path).read_bytes()

        async def send() -> httpx.Response:
            return await self._client.post(self._url("/ref"), data={"session_id": session_id, "ref_text": ref_text},
                                           files={"audio": ("ref.wav", audio, "audio/wav")})

        return dict((await request_with_retry(send, what="gpu_voice.ref")).json())

    async def synth(self, session_id: str, text: str, lang: str) -> tuple[bytes, int]:
        """One line in the session's copied voice -> (PCM16 mono, sample rate)."""
        async def send() -> httpx.Response:
            return await self._client.post(self._url("/tts"), json={
                "session_id": session_id, "text": text, "lang": lang, "speed": self.s.gpu_voice_speed})

        t0 = time.perf_counter()
        resp = await request_with_retry(send, what="gpu_voice.tts", retries=0)
        self.last_latency_s = time.perf_counter() - t0
        try:
            self.last_synth_ms = float(resp.headers.get("x-synth-ms", ""))
        except ValueError:
            self.last_synth_ms = None
        if len(resp.content) < 2:
            raise ProviderError("gpu_voice.tts: empty audio")
        return resp.content[: len(resp.content) // 2 * 2], int(resp.headers.get("x-sample-rate", "24000"))

    async def health(self) -> dict[str, Any]:
        resp = await self._client.get(self._url("/health"), timeout=3.0)
        resp.raise_for_status()
        return dict(resp.json())
