"""Gnani Prisma STT: REST (Studio) and realtime WebSocket (Live). See SPEC.md 6.1 / 6.2."""
import asyncio
import json
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import websockets

from app.config import Settings, get_settings
from app.providers.base import ProviderError, STTResult, TranscriptEvent
from app.providers.http import gnani_gate, request_with_retry

MODEL = "prisma-v3.0"
FRAME_BYTES = 1024          # docs: exactly 1024-byte frames
FRAME_SECONDS = 512 / 16000  # 32 ms of 16 kHz PCM16 mono
MIME = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".flac": "audio/flac",
        ".aac": "audio/aac", ".m4a": "audio/mp4"}


class GnaniSTT:
    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None) -> None:
        self.s = settings or get_settings()
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))

    def _key(self) -> str:
        key = self.s.gnani_api_key.get_secret_value()
        if not key:
            raise ProviderError("GNANI_API_KEY is not set")
        return key

    async def transcribe(self, wav_path: str, lang: str = "indic-auto", *, fmt: str | None = None,
                         keyterms: list[str] | None = None) -> STTResult:
        path = Path(wav_path)
        audio = path.read_bytes()
        data: dict[str, str] = {"model": MODEL, "language_code": lang}
        if fmt:
            data["format"] = fmt
        if keyterms:
            data["keyterms"] = json.dumps(keyterms[:200], ensure_ascii=False)
        headers = {"X-API-Key-ID": self._key()}
        mime = MIME.get(path.suffix.lower(), "application/octet-stream")

        async def send() -> httpx.Response:
            files = {"audio_file": (path.name, audio, mime)}
            return await self._client.post(f"{self.s.gnani_base}/stt/v3", headers=headers, data=data, files=files)

        t0 = time.perf_counter()
        async with gnani_gate(self.s.gnani_max_concurrency):
            resp = await request_with_retry(send, what="stt.transcribe")
        latency = time.perf_counter() - t0
        return parse_rest_response(resp.json(), latency)

    async def stream(self, pcm_frames: AsyncIterator[bytes], lang: str = "indic-auto", *,
                     sample_rate: int = 16000, pace: bool = False,
                     extra_headers: dict[str, str] | None = None) -> AsyncIterator[TranscriptEvent]:
        """Send PCM16 mono audio, yield transcript events until the input ends and the socket drains.

        Input chunks of any size are re-framed to exactly 1024 bytes. Set `pace=True` when replaying
        a file (the docs forbid bursting); live mic input is already real-time.
        """
        headers = {"x-api-key-id": self._key(), "model": MODEL, "language_code": lang,
                   "x-sample-rate": str(sample_rate), **(extra_headers or {})}
        url = f"{self.s.gnani_ws_base}/stt/v3/stream"
        queue: asyncio.Queue[TranscriptEvent | None] = asyncio.Queue()
        frame_s = 512 / sample_rate

        async with websockets.connect(url, additional_headers=headers, max_size=2**22) as ws:
            async def sender() -> None:
                buf, t_next = b"", time.perf_counter()
                async for chunk in pcm_frames:
                    buf += chunk
                    while len(buf) >= FRAME_BYTES:
                        await ws.send(buf[:FRAME_BYTES])
                        buf = buf[FRAME_BYTES:]
                        if pace:
                            t_next += frame_s
                            await asyncio.sleep(max(0.0, t_next - time.perf_counter()))
                if buf:
                    await ws.send(buf.ljust(FRAME_BYTES, b"\x00"))
                # ~1 s of silence so the last utterance finalises, then commit.
                silence = b"\x00" * FRAME_BYTES
                for _ in range(int(1.0 / frame_s)):
                    await ws.send(silence)
                    if pace:
                        await asyncio.sleep(frame_s)
                await ws.send(json.dumps({"type": "commit"}))

            async def receiver() -> None:
                try:
                    async for msg in ws:
                        if isinstance(msg, str):
                            ev = parse_ws_message(msg)
                            if ev:
                                await queue.put(ev)
                except websockets.ConnectionClosed:
                    pass
                finally:
                    await queue.put(None)

            send_task = asyncio.create_task(sender())
            recv_task = asyncio.create_task(receiver())
            try:
                drain_deadline: float | None = None
                while True:
                    if send_task.done() and drain_deadline is None:
                        send_task.result()  # surface sender errors
                        drain_deadline = time.perf_counter() + 4.0
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
                        drain_deadline = time.perf_counter() + 1.5
            finally:
                send_task.cancel()
                recv_task.cancel()


def parse_rest_response(j: dict[str, Any], latency_s: float) -> STTResult:
    if not j.get("success", False):
        err = j.get("error") or {}
        msg = err.get("message") if isinstance(err, dict) else str(err)
        raise ProviderError(f"stt.transcribe: {msg or j}")
    return STTResult(
        text=(j.get("transcript") or "").strip(),
        detected_lang=j.get("detected_language_code"),
        request_id=j.get("request_id"),
        processing_time=j.get("processing_time"),
        latency_s=latency_s,
        raw=j,
    )


def parse_ws_message(msg: str) -> TranscriptEvent | None:
    try:
        j = json.loads(msg)
    except ValueError:
        return None
    t = j.get("type")
    if t == "transcript":
        return TranscriptEvent(
            kind="final", text=(j.get("text") or "").strip(), segment_id=j.get("segment_id"),
            utterance_id=j.get("utterance_id"), detected_lang=j.get("detected_language_code"),
            server_latency=j.get("latency"), audio_duration_ms=j.get("audio_duration_ms"),
        )
    if t in ("connected", "speech_start", "processing"):
        return TranscriptEvent(kind=t, utterance_id=j.get("utterance_id"))
    if t == "error":
        return TranscriptEvent(kind="error", message=str(j.get("message", "")))
    return None
