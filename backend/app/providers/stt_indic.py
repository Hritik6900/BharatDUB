"""Speech-to-text from the Indic Transcribe server (gpu_engine_v1/transcribe_server.py, :9043), for Studio HQ.
Not streaming, clips of up to 30 s; it hears the Indian languages, so it can also hear a dubbed line back."""
import time
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.providers.base import ProviderError, STTResult
from app.providers.http import request_with_retry


class IndicTranscribeSTT:
    name = "indic_transcribe"

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None) -> None:
        self.s = settings or get_settings()
        self.url = self.s.v1_transcribe_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=3.0))

    async def transcribe(self, wav_path: str, lang: str = "hi-IN", **_: Any) -> STTResult:
        path = Path(wav_path)
        audio = path.read_bytes()

        async def send() -> httpx.Response:
            return await self._client.post(self.url + "/stt", data={"lang": lang},
                                           files={"audio": (path.name, audio, "application/octet-stream")})

        t0 = time.perf_counter()
        try:
            j = (await request_with_retry(send, what="indic_transcribe")).json()
        except (httpx.HTTPError, ValueError) as e:
            raise ProviderError(f"indic_transcribe: {e}") from e
        return STTResult(text=(j.get("text") or "").strip(), detected_lang=j.get("lang") or lang,
                         processing_time=(j.get("ms") or 0) / 1000, latency_s=time.perf_counter() - t0, raw=j)
