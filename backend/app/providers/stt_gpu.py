"""Speech-to-text on our own GPU machine (`gpu_engine/stt_engine.py`), used when `AI_MODE=gpu`.

The engine speaks the hosted realtime service's event names, so both are read by one parser. Its model
(Whisper-Hindi2Hinglish-Apex) hears Hindi and Hinglish only and writes them in Latin letters; any other language, and
any failure, goes to the hosted service when one is configured (`backup`).
"""
import asyncio
import json
import re
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
import websockets

from app.config import Settings, get_settings
from app.providers.base import ProviderError, STTResult, TranscriptEvent
from app.providers.http import request_with_retry
from app.providers.stt_gnani import FRAME_BYTES, parse_ws_message

HEARS = {"hi-IN", "hi", "indic-auto", "hi-IN,en-IN"}
NOISE_AT_START = re.compile(r"^(?:nan[\s,.]+)+", re.IGNORECASE)
RETURN_CHECK_S = 15.0   # while on the hosted stream: how often the engine is asked whether it is back


def without_noise(text: str) -> str:
    """A transcript without the model's noise word: alone ("nan") or before speech ("nan everyone, welcome")."""
    text = NOISE_AT_START.sub("", text)
    return "" if not_speech(text) else text


def not_speech(text: str) -> bool:
    """The model writes "nan" for sound that is not speech (9 of 1000 lines on a real stream, one was dubbed)."""
    return text.strip(" .?!,").lower() == "nan"


class GpuSTT:
    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None,
                 backup: Any = None) -> None:
        self.s = settings or get_settings()
        self.url = self.s.gpu_stt_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=3.0))
        self.backup = backup
        self.fell_back = 0   # calls answered by the backup

    async def transcribe(self, wav_path: str, lang: str = "indic-auto", *, fmt: str | None = None,
                         keyterms: list[str] | None = None) -> STTResult:
        if lang not in HEARS:
            if self.backup is None:
                raise ProviderError(f"gpu_stt: the GPU model hears Hindi and Hinglish only, not {lang}")
            self.fell_back += 1
            return await self.backup.transcribe(wav_path, lang, fmt=fmt, keyterms=keyterms)
        path = Path(wav_path)
        audio = path.read_bytes()

        async def send() -> httpx.Response:
            return await self._client.post(self.url + "/stt", data={"lang": lang},
                                           files={"audio": (path.name, audio, "application/octet-stream")})

        t0 = time.perf_counter()
        try:
            j = (await request_with_retry(send, what="gpu_stt.transcribe")).json()
        except (ProviderError, httpx.HTTPError, ValueError) as e:
            if self.backup is None:
                raise ProviderError(f"gpu_stt.transcribe: {e}") from e
            self.fell_back += 1
            return await self.backup.transcribe(wav_path, lang, fmt=fmt, keyterms=keyterms)
        text = (j.get("text") or "").strip()
        return STTResult(text=without_noise(text), detected_lang="hi-IN",
                         processing_time=(j.get("ms") or 0) / 1000, latency_s=time.perf_counter() - t0, raw=j)

    async def stream(self, pcm_frames: AsyncIterator[bytes], lang: str = "indic-auto", *,
                     sample_rate: int = 16000, pace: bool = False,
                     extra_headers: dict[str, str] | None = None) -> AsyncIterator[TranscriptEvent]:
        """Same contract as the hosted stream: PCM16 mono in, transcript events out until the input ends."""
        h = extra_headers or {}
        query = {"min_silence_ms": h.get("x-min-silence-ms", "500"),
                 "partial_interval_ms": h.get("x-partial-interval-ms", str(self.s.live_partial_interval_ms))}
        url = self.url.replace("https://", "wss://").replace("http://", "ws://") + "/stream?" + urlencode(query)
        try:
            if lang not in HEARS or sample_rate != 16000:
                raise ProviderError(f"gpu_stt: not for {lang} at {sample_rate} Hz")
            ws = await websockets.connect(url, max_size=2**22, open_timeout=4)
        except Exception as e:  # noqa: BLE001 - engine down or another language: the hosted service takes the stream
            if self.backup is None:
                raise ProviderError(f"gpu_stt.stream: {e}") from e
            self.fell_back += 1
            # The hosted stream is not kept for good: seen 2026-11-21 on a real stream, the tunnel dropped for a few
            # seconds and the session then stayed on the hosted service for as long as that connection lived. So the
            # engine is asked now and then, and once it answers the hosted stream is ended after an utterance's final
            # (nobody is mid-sentence then); the caller connects again and lands on the engine.
            can_return = lang in HEARS and sample_rate == 16000
            checked = time.perf_counter()
            back = False
            async for ev in self.backup.stream(pcm_frames, lang, sample_rate=sample_rate, pace=pace,
                                               extra_headers=extra_headers):
                yield ev
                if can_return and not back and time.perf_counter() - checked >= RETURN_CHECK_S:
                    checked = time.perf_counter()
                    back = bool((await self.health()).get("ok"))
                if back and ev.kind == "final":
                    return
            return
        queue: asyncio.Queue[TranscriptEvent | None] = asyncio.Queue()
        frame_s = 512 / sample_rate

        async def sender() -> None:
            t_next = time.perf_counter()
            async for chunk in pcm_frames:
                await ws.send(chunk)
                if pace:
                    t_next += len(chunk) / 2 / sample_rate
                    await asyncio.sleep(max(0.0, t_next - time.perf_counter()))
            for _ in range(int(1.0 / frame_s)):   # a second of silence so the last utterance closes
                await ws.send(b"\x00" * FRAME_BYTES)
                if pace:
                    await asyncio.sleep(frame_s)
            await ws.send(json.dumps({"type": "commit"}))

        async def receiver() -> None:
            try:
                async for msg in ws:
                    if isinstance(msg, str):
                        ev = parse_ws_message(msg)
                        if ev and ev.kind in ("partial", "final"):   # the model's word for noise is nothing to dub
                            ev.text, ev.stable_text = without_noise(ev.text), without_noise(ev.stable_text)
                        if ev:
                            await queue.put(ev)
            except websockets.ConnectionClosed:
                pass
            finally:
                await queue.put(None)

        send_task, recv_task = asyncio.create_task(sender()), asyncio.create_task(receiver())
        try:
            drain_deadline: float | None = None
            while True:
                if send_task.done() and drain_deadline is None:
                    send_task.result()
                    drain_deadline = time.perf_counter() + 3.0
                timeout = 0.25 if drain_deadline is None else max(0.0, drain_deadline - time.perf_counter())
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=timeout)
                except TimeoutError:
                    if drain_deadline is not None and time.perf_counter() >= drain_deadline:
                        break
                    continue
                if ev is None:
                    break
                yield ev
                if drain_deadline is not None and ev.kind == "final":
                    drain_deadline = time.perf_counter() + 1.0
        finally:
            send_task.cancel()
            recv_task.cancel()
            await ws.close()

    async def health(self) -> dict[str, Any]:
        t0 = time.perf_counter()
        try:
            r = await self._client.get(self.url + "/health", timeout=3.0)
            return {**(r.json() if r.status_code == 200 else {}), "ok": r.status_code == 200,
                    "ms": round((time.perf_counter() - t0) * 1000)}
        except httpx.HTTPError as e:
            return {"ok": False, "error": type(e).__name__}
