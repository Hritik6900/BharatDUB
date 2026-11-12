"""Gnani Timbre TTS + Vachana voice cloning. See SPEC.md 6.3 / 6.4."""
import base64
import json
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.providers.base import ProviderError, SpeakerEmbedding, VoiceSpec
from app.providers.http import gnani_gate, request_with_retry

VC_MODEL = "vachana-vc-v1"


class ConsentRequired(ProviderError):
    """Raised when cloning is attempted without recorded consent (golden rule 4)."""


class GnaniTTS:
    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None) -> None:
        self.s = settings or get_settings()
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=10.0))
        self.last_latency_s: float | None = None
        self.last_first_chunk_s: float | None = None

    def _headers(self, json_body: bool = True) -> dict[str, str]:
        key = self.s.gnani_api_key.get_secret_value()
        if not key:
            raise ProviderError("GNANI_API_KEY is not set")
        h = {"X-API-Key-ID": key}
        if json_body:
            h["Content-Type"] = "application/json"
        return h

    def build_body(self, text: str, lang: str, voice: VoiceSpec, *, container: str = "wav",
                   sample_rate: int | None = None) -> dict[str, Any]:
        audio_config = {"sample_rate": sample_rate or self.s.tts_sample_rate, "num_channels": 1, "sample_width": 2,
                        "encoding": "linear_pcm", "container": container}
        if voice["kind"] == "clone":
            # VC takes no voice/language field (docs 2026-11-13).
            return {"text": text, "model": VC_MODEL, "speaker_embedding": dict(voice["embedding"]),
                    "audio_config": audio_config}
        return {"text": text, "voice": voice["voice"], "model": self.s.tts_model, "language": lang,
                "speed": 1.0, "audio_config": audio_config}

    async def synth(self, text: str, lang: str, voice: VoiceSpec) -> bytes:
        """Full WAV bytes."""
        body = self.build_body(text, lang, voice, container="wav")
        headers = self._headers()

        async def send() -> httpx.Response:
            return await self._client.post(f"{self.s.gnani_base}/api/v1/tts/inference", headers=headers, json=body)

        t0 = time.perf_counter()
        async with gnani_gate(self.s.gnani_max_concurrency):
            resp = await request_with_retry(send, what="tts.synth")
        self.last_latency_s = time.perf_counter() - t0
        if resp.headers.get("content-type", "").startswith("application/json"):
            raise ProviderError(f"tts.synth: expected audio, got JSON {resp.text[:200]}")
        if not resp.content:
            raise ProviderError("tts.synth: empty audio")
        return resp.content

    async def synth_stream(self, text: str, lang: str, voice: VoiceSpec, *,
                           sample_rate: int | None = None) -> AsyncIterator[bytes]:
        """Raw PCM16 mono chunks (default settings.tts_sample_rate), via SSE. Records time to first chunk."""
        body = self.build_body(text, lang, voice, container="raw", sample_rate=sample_rate)
        headers = self._headers()
        t0 = time.perf_counter()
        self.last_first_chunk_s = None
        async with gnani_gate(self.s.gnani_max_concurrency):
            async with self._client.stream("POST", f"{self.s.gnani_base}/api/v1/tts/sse",
                                           headers=headers, json=body) as resp:
                if resp.status_code >= 400:
                    await resp.aread()
                    raise ProviderError(f"tts.synth_stream: HTTP {resp.status_code} {resp.text[:200]}",
                                        status=resp.status_code, retryable=resp.status_code in (429, 500, 502, 503))
                async for event, data in iter_sse(resp.aiter_lines()):
                    if event == "error":
                        raise ProviderError(f"tts.synth_stream: {data[:200]}")
                    if event not in ("chunk", "complete"):
                        continue
                    payload = json.loads(data) if data else {}
                    audio_b64 = payload.get("audio") or ""
                    if audio_b64:
                        if self.last_first_chunk_s is None:
                            self.last_first_chunk_s = time.perf_counter() - t0
                        yield base64.b64decode(audio_b64)
                    if event == "complete" or payload.get("is_final"):
                        break
        self.last_latency_s = time.perf_counter() - t0

    async def clone_embedding(self, wav_path: str, *, consent_at: str | None) -> SpeakerEmbedding:
        """Speaker embedding from 5-30 s of clean speech. Refuses without recorded consent."""
        if not consent_at:
            raise ConsentRequired("voice cloning requires a voice profile with consent_at set", status=403)
        path = Path(wav_path)
        audio = path.read_bytes()
        headers = self._headers(json_body=False)

        async def send() -> httpx.Response:
            files = {"audio_file": (path.name, audio, "audio/wav")}
            return await self._client.post(f"{self.s.gnani_base}/api/v1/tts/voice-clone/embeddings",
                                           headers=headers, files=files)

        t0 = time.perf_counter()
        async with gnani_gate(self.s.gnani_max_concurrency):
            resp = await request_with_retry(send, what="tts.clone_embedding")
        self.last_latency_s = time.perf_counter() - t0
        return parse_embedding(resp.json())


def parse_embedding(j: dict[str, Any]) -> SpeakerEmbedding:
    # Docs: {"success", "message", "data": {"voice_clone_embedding": {embedding, shape, dtype}}}
    emb = (j.get("data") or {}).get("voice_clone_embedding") or j
    if not isinstance(emb, dict) or "embedding" not in emb:
        raise ProviderError(f"tts.clone_embedding: unexpected response keys {list(j)}")
    return {"embedding": emb["embedding"], "shape": list(emb.get("shape") or [1, 768]),
            "dtype": emb.get("dtype") or "torch.bfloat16"}


async def iter_sse(lines: AsyncIterator[str]) -> AsyncIterator[tuple[str, str]]:
    """Minimal SSE parser: yields (event, data) per blank-line-terminated block."""
    event, data = "message", []
    async for line in lines:
        if line == "":
            if data:
                yield event, "\n".join(data)
            event, data = "message", []
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip())
    if data:
        yield event, "\n".join(data)
