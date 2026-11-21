"""A provider with a second one behind it: when a call to the first fails, the second answers (golden rule 8)."""
import logging
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

    @property
    def last_latency_s(self) -> float | None:
        return getattr(self.first, "last_latency_s", None)
