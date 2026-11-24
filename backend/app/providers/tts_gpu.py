"""Our own GPU voice engine (IndicF5 on an A100, `voice_engine_live.py` on that machine): zero-shot voice cloning for Live.

It is not a Gnani model. It exists because a cloned line from Gnani takes 2-3.5 s and the account runs one request
at a time, so a copied voice could not keep up with a live speaker (measured 2026-11-14: 5 of 21 phrases).
Measured on the A100 the same day: 0.91 s for a line whatever its length, and three lines at once in 1.2 s when each
runs in its own engine process (2.3 s as replicas inside one process).

Off unless `GPU_VOICE_URL` is set: one URL, or several separated by commas (one engine process each; a line goes to
the least busy one). The engines listen only on their own machine; reach them through an SSH tunnel.

  POST /ref   multipart: session_id, ref_text, audio          -> remembers the reference voice (3-10 s) for that session
  POST /tts   json {session_id, text, lang, speed, fmt, nfe}  -> audio at X-Sample-Rate (24 kHz): raw PCM16, or OGG/Opus
"""
import asyncio
import io
import time
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import soundfile as sf

from app.config import Settings, get_settings
from app.providers.base import ProviderError
from app.providers.http import request_with_retry
from app.providers.tts_gnani import ConsentRequired

# IndicF5 speaks these; English is not among them (it stays on the Gnani voices).
GPU_LANGS = {"hi-IN", "ta-IN", "te-IN", "bn-IN", "kn-IN", "ml-IN", "mr-IN", "gu-IN", "pa-IN"}


class GpuVoice:
    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None) -> None:
        self.s = settings or get_settings()
        self.urls = [u.strip().rstrip("/") for u in self.s.gpu_voice_url.split(",") if u.strip()]
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(self.s.gpu_voice_timeout_s, connect=3.0))
        self._busy = [0] * len(self.urls)
        self._has_ref: dict[str, set[int]] = {}   # session -> engines that hold its voice
        self._steps: dict[str, int] = {}          # session -> denoising steps for its lines (else gpu_voice_steps)
        # Set in `AI_MODE=gpu`: turns a sample text in Latin letters into Devanagari before the engines get it.
        self.ref_text_fix: Any = None
        self.last_synth_ms: float | None = None   # the engine's own time for the last line
        self.last_latency_s: float | None = None  # ... and the whole round trip
        self.breakers: list[Any] | None = None    # v1 (`V1_BREAKER`): one per engine; None = calls go out as always

    @property
    def enabled(self) -> bool:
        return bool(self.urls)

    @property
    def capacity(self) -> int:
        """Lines that can be made at once: one per engine process."""
        return max(1, len(self.urls))

    def speaks(self, lang: str) -> bool:
        return self.enabled and lang in GPU_LANGS

    async def set_ref(self, session_id: str, wav_path: str, ref_text: str, *, consent_at: str | None,
                      steps: int | None = None) -> dict[str, Any]:
        """Give every engine the voice to copy: 3-10 s of speech and exactly what is said in it.
        Refuses without recorded consent (golden rule 4), like every other cloning call.
        `steps`: denoising steps for this voice's lines (None = `gpu_voice_steps`, 0 = the engine's own)."""
        if not consent_at:
            raise ConsentRequired("voice cloning requires recorded consent", status=403)
        if steps is not None:
            self._steps[session_id] = steps
        if self.ref_text_fix is not None:
            ref_text = await self.ref_text_fix(ref_text)
        audio = Path(wav_path).read_bytes()

        async def one(i: int) -> dict[str, Any]:
            async def send() -> httpx.Response:
                return await self._client.post(self.urls[i] + "/ref", data={"session_id": session_id, "ref_text": ref_text},
                                               files={"audio": ("ref.wav", audio, "audio/wav")}, timeout=20.0)
            if self.breakers is None:
                return dict((await request_with_retry(send, what="gpu_voice.ref")).json())
            from app.v1 import breaker
            limit = self.s.v1_breaker_voice_timeout_s * breaker.REF_TIMEOUT_FACTOR
            return dict((await breaker.call(self.breakers[i], lambda: request_with_retry(send, what="gpu_voice.ref"),
                                            limit)).json())

        res = await asyncio.gather(*(one(i) for i in range(len(self.urls))), return_exceptions=True)
        ok = {i for i, r in enumerate(res) if not isinstance(r, BaseException)}
        if not ok:
            raise ProviderError(f"gpu_voice.ref: no engine took the sample ({res[0]})")
        self._has_ref[session_id] = ok
        return {"ok": True, "engines": len(ok)}

    async def synth(self, session_id: str, text: str, lang: str, speed: float | None = None) -> tuple[bytes, int]:
        """One line in the session's copied voice -> (PCM16 mono, sample rate). `speed` > 1 = faster speech."""
        ready = self._has_ref.get(session_id) or set(range(len(self.urls)))
        if self.breakers is not None:   # an engine whose circuit is open is not asked; none left = fail at once
            ready = {k for k in ready if not self.breakers[k].blocked()}
            if not ready:
                from app.v1.breaker import CircuitOpen
                raise CircuitOpen("gpu_voice.tts: every engine's circuit is open", retryable=True)
        i = min(ready, key=lambda k: self._busy[k])
        body = {"session_id": session_id, "text": text, "lang": lang, "fmt": self.s.gpu_voice_format,
                "speed": round(speed or self.s.gpu_voice_speed, 3)}
        steps = self._steps.get(session_id, self.s.gpu_voice_steps)
        if steps > 0:
            body["nfe"] = steps

        async def send() -> httpx.Response:
            return await self._client.post(self.urls[i] + "/tts", json=body)

        self._busy[i] += 1
        t0 = time.perf_counter()
        try:
            if self.breakers is None:
                resp = await request_with_retry(send, what="gpu_voice.tts", retries=0)
            else:
                from app.v1 import breaker
                resp = await breaker.call(self.breakers[i], lambda: request_with_retry(send, what="gpu_voice.tts", retries=0),
                                          self.s.v1_breaker_voice_timeout_s)
        finally:
            self._busy[i] -= 1
        self.last_latency_s = time.perf_counter() - t0
        try:
            self.last_synth_ms = float(resp.headers.get("x-synth-ms", ""))
        except ValueError:
            self.last_synth_ms = None
        rate = int(resp.headers.get("x-sample-rate", "24000"))
        if resp.headers.get("x-format") in ("mp3", "opus"):   # a compressed file: decode it (libsndfile reads both)
            x, rate = sf.read(io.BytesIO(resp.content), dtype="int16", always_2d=False)
            pcm = np.ascontiguousarray(x).astype("<i2").tobytes()
        else:
            pcm = resp.content[: len(resp.content) // 2 * 2]
        if len(pcm) < 2:
            raise ProviderError("gpu_voice.tts: empty audio")
        return pcm, int(rate)

    async def health(self) -> list[dict[str, Any]]:
        out = []
        for u in self.urls:
            t0 = time.perf_counter()
            try:
                r = await self._client.get(u + "/health", timeout=3.0)
                out.append({**(r.json() if r.status_code == 200 else {}), "ok": r.status_code == 200})
            except httpx.HTTPError as e:
                out.append({"ok": False, "error": type(e).__name__})
            out[-1]["ms"] = round((time.perf_counter() - t0) * 1000)   # this engine's own round trip
        return out
