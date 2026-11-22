"""Client for the QA server (gpu_engine_v1/qa_server.py, :9045): hears a dubbed line back, compares its voice
with the speaker's, and tells speakers apart.

  POST /score    multipart audio, text, lang, [ref]  -> {heard, backcheck, similarity}
  POST /diarize  multipart audio                     -> {segments: [{start, end, speaker}]}
"""
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.providers.base import ProviderError


class QAClient:
    name = "qa_server"

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None) -> None:
        self.s = settings or get_settings()
        self.url = self.s.v1_qa_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=3.0))

    async def score(self, wav: Path, text: str, lang: str, ref_wav: Path | None = None) -> dict[str, Any]:
        files: dict[str, Any] = {"audio": (wav.name, wav.read_bytes(), "audio/wav")}
        if ref_wav is not None and ref_wav.exists():
            files["ref"] = (ref_wav.name, ref_wav.read_bytes(), "audio/wav")
        try:
            r = await self._client.post(self.url + "/score", data={"text": text, "lang": lang}, files=files)
            r.raise_for_status()
            j = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise ProviderError(f"qa.score: {e}") from e
        return {"heard": j.get("heard") or "", "backcheck": j.get("backcheck"), "similarity": j.get("similarity")}

    async def diarize(self, wav: Path) -> list[dict[str, Any]]:
        try:
            r = await self._client.post(self.url + "/diarize",
                                        files={"audio": (wav.name, wav.read_bytes(), "audio/wav")})
            r.raise_for_status()
            return list(r.json().get("segments") or [])
        except (httpx.HTTPError, ValueError) as e:
            raise ProviderError(f"qa.diarize: {e}") from e
