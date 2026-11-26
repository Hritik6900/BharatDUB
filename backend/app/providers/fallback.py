"""A provider with a second one behind it: when a call to the first fails, the second answers (golden rule 8)."""
import logging
from collections.abc import AsyncIterator
from typing import Any

from app.providers.base import ProviderError

log = logging.getLogger("bharatdub.providers")


class FallbackLLM:
    """The translation model on our GPU first; the hosted one when it fails. Both are `OpenAILLM`-shaped."""

    def __init__(self, first: Any, second: Any | None) -> None:
        self.first, self.second = first, second
        self.fell_back = 0

    async def _call(self, name: str, *args: Any, **kw: Any) -> Any:
        try:
            return await getattr(self.first, name)(*args, **kw)
        except (ProviderError, TimeoutError) as e:
            if self.second is None:
                raise
            self.fell_back += 1
            log.warning("llm: %s failed on the GPU model (%s), the hosted model answers", name, str(e)[:120])
            return await getattr(self.second, name)(*args, **kw)

    async def translate_batch(self, lines: list[str], target: str, glossary: list[str]) -> list[str]:
        return await self._call("translate_batch", lines, target, glossary)  # type: ignore[no-any-return]

    async def translate_chunk(self, text: str, target: str, glossary: list[str], context: list[str],
                              **kw: Any) -> str:
        return await self._call("translate_chunk", text, target, glossary, context, **kw)  # type: ignore[no-any-return]

    async def shorten(self, text: str, target: str, max_seconds: float, **kw: Any) -> str:
        return await self._call("shorten", text, target, max_seconds, **kw)  # type: ignore[no-any-return]

    async def judge_lines(self, pairs: list[tuple[str, str]], target: str) -> list[dict[str, bool]]:
        return await self._call("judge_lines", pairs, target)  # type: ignore[no-any-return]

    @property
    def last_latency_s(self) -> float | None:
        return getattr(self.first, "last_latency_s", None)


class FallbackSTT:
    """Speech-to-text with a second one behind it. In the GPU engine the hosted service is first by default
    (`gpu_stt_first`): measured 2026-11-21 on 24 class lines, key words right out of 80, hosted / our GPU model:
    clean 77 / 70, hard (faster, echo, noise) 73 / 49. Our GPU model answers when the hosted one fails."""

    def __init__(self, first: Any, second: Any | None) -> None:
        self.first, self.second = first, second
        self.fell_back = 0

    async def transcribe(self, wav_path: str, lang: str = "indic-auto", **kw: Any) -> Any:
        try:
            return await self.first.transcribe(wav_path, lang, **kw)
        except Exception as e:  # noqa: BLE001
            if self.second is None:
                raise
            self.fell_back += 1
            log.warning("stt: transcribe failed on the first service (%s), the second answers", str(e)[:120])
            return await self.second.transcribe(wav_path, lang, **kw)

    async def stream(self, pcm_frames: AsyncIterator[bytes], lang: str = "indic-auto", **kw: Any) -> AsyncIterator[Any]:
        """The first service's stream; when it cannot start (or dies before saying anything), the second takes the
        audio. A stream that fails later ends here: the caller connects again and the first is tried again."""
        got = False
        try:
            async for ev in self.first.stream(pcm_frames, lang, **kw):
                got = True
                yield ev
            return
        except Exception as e:  # noqa: BLE001
            if got or self.second is None:
                raise
            self.fell_back += 1
            log.warning("stt: the first service's stream did not start (%s), the second takes it", str(e)[:120])
        async for ev in self.second.stream(pcm_frames, lang, **kw):
            yield ev

    async def health(self) -> dict[str, Any]:
        h = getattr(self.second, "health", None)
        return await h() if h else {"ok": True}
