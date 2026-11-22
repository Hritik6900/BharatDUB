"""One interface per step: `transcribe()`, `translate()`, `speak()`, `separate()`, `diarize()`, `score()`.

Each call walks the step's provider list from `config/routing.yaml`: a provider gets the step's timeout, and when
it fails or runs out of time the next one is tried and the reason is logged (and traced with `V1_TRACE`).
Used by the HQ Studio path; the Live pipeline keeps the provider objects it has always used.
"""
import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar

from app.providers.base import ProviderError, STTResult, VoiceSpec
from app.v1 import trace
from app.v1.router import Router, get_router

log = logging.getLogger("bharatdub.stages")
T = TypeVar("T")


class StageFailed(ProviderError):
    """Every provider of a step failed. `reasons` has one line per provider."""

    def __init__(self, stage: str, reasons: list[str]) -> None:
        super().__init__(f"{stage}: " + ("; ".join(reasons) if reasons else "no provider is configured"))
        self.stage, self.reasons = stage, reasons


class Stages:
    def __init__(self, mode: str = "studio_hq", engine: str = "cloud", router: Router | None = None,
                 key: str = "") -> None:
        self.mode, self.engine, self.key = mode, engine, key
        self.r = router or get_router()
        self.fallbacks: list[dict[str, str]] = []      # every time a provider was passed over, and why
        self.used: dict[str, str] = {}                 # step -> the provider that answered last
        self._sticky: dict[str, str] = {}              # voice: the provider this job or session speaks with
        self._tts: dict[str, Any] = {}

    # ---------- the walk ----------
    async def _run(self, stage: str, names: list[str], call: Callable[[str], Awaitable[T]],
                   timeout: float | None = None) -> T:
        reasons: list[str] = []
        limit = timeout or self.r.timeout(stage)
        for i, name in enumerate(names):
            try:
                out = await asyncio.wait_for(call(name), limit)
                self.used[stage] = name
                return out
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - any failure moves on to the next provider
                why = (f"timed out after {limit:.0f} s" if isinstance(e, TimeoutError)
                       else f"{type(e).__name__}: {str(e)[:140]}")
                reasons.append(f"{name}: {why}")
                nxt = names[i + 1] if i + 1 < len(names) else None
                self.fallbacks.append({"stage": stage, "provider": name, "reason": why, "next": nxt or ""})
                log.warning("%s: %s failed (%s)%s", stage, name, why, f", trying {nxt}" if nxt else "")
                if trace.enabled():
                    trace.event("fallback", stage=stage, mode=self.mode, engine=self.engine, provider=name,
                                reason=why, next=nxt, key=self.key)
                    trace.FALLBACKS.labels(stage, self.mode).inc()
        raise StageFailed(stage, reasons)

    def names(self, stage: str) -> list[str]:
        return self.r.chain(self.mode, self.engine, stage)

    # ---------- the six steps ----------
    async def transcribe(self, wav: str | Path, lang: str = "indic-auto", **kw: Any) -> STTResult:
        """The first provider that hears the clip."""
        async def call(name: str) -> STTResult:
            stt = self.r.provider("stt", name)
            return await stt.transcribe(str(wav), lang, **_stt_kw(name, kw))  # type: ignore[no-any-return]
        return await self._run("transcribe", self.names("transcribe"), call)

    async def transcribe_each(self, wav: str | Path, lang: str = "indic-auto", **kw: Any) -> dict[str, str]:
        """Every provider's transcript of the clip (those that answered), for merging two hearings into one."""
        names = self.names("transcribe")
        limit = self.r.timeout("transcribe")

        async def one(name: str) -> str | None:
            try:
                stt = self.r.provider("stt", name)
                res = await asyncio.wait_for(stt.transcribe(str(wav), lang, **_stt_kw(name, kw)), limit)
                return str(res.text or "").strip()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                self.fallbacks.append({"stage": "transcribe", "provider": name, "reason": str(e)[:140], "next": ""})
                return None
        got = await asyncio.gather(*(one(n) for n in names))
        return {n: t for n, t in zip(names, got) if t is not None}

    def llm(self, stage: str = "translate") -> Any:
        """The model chain of a text step (an object with `translate_batch`, `translate_chunk`, `shorten`)."""
        return self.r.llm(self.mode, self.engine, stage)

    async def translate(self, lines: list[str], target: str, glossary: list[str]) -> list[str]:
        async def call(name: str) -> list[str]:
            return await self.r.provider("llm", name).translate_batch(lines, target, glossary)  # type: ignore[no-any-return]
        limit = max(self.r.timeout("translate"), 6.0 * len(lines))
        return await self._run("translate", self.names("translate"), call, timeout=limit)

    async def chat(self, system: str, user: str, *, stage: str = "translate", max_tokens: int = 3000,
                   temperature: float = 0.2) -> str:
        """A free-form call to a text step's model chain (the text work of the HQ path)."""
        async def call(name: str) -> str:
            llm = self.r.provider("llm", name)
            return await llm._chat(system, user, temperature=temperature, max_tokens=max_tokens)  # type: ignore[no-any-return]
        names = self.names(stage) or self.names("translate")
        return await self._run(stage, names, call, timeout=self.r.timeout("review"))

    def _speaker(self, name: str) -> Any:
        if name not in self._tts:
            if name == "indicf5":
                from app.providers.tts_gpu_studio import GpuStudioTTS
                self._tts[name] = GpuStudioTTS(self.r.gpu_voice(self.mode, self.engine),
                                               self.r.stt(self.mode, self.engine), self.r.s, backup=None)
            else:
                self._tts[name] = self.r.provider("tts", name)
        return self._tts[name]

    def own_voice(self, lang: str, voice: VoiceSpec) -> bool:
        """This line would be spoken by our voice engine (a copied voice with an engine sample, in a language it speaks)."""
        if "indicf5" not in self.names("speak") or voice["kind"] != "clone":
            return False
        return bool(dict(voice["embedding"]).get("ref_path")) and self._speaker("indicf5").gpu.speaks(lang)

    async def speak(self, text: str, lang: str, voice: VoiceSpec, *, speed: float = 1.0) -> bytes:
        """One line as WAV bytes. The provider that spoke this job's first line keeps speaking it (one voice),
        and another one answers only when that one fails."""
        names = self.names("speak")
        if not self.own_voice(lang, voice):
            names = [n for n in names if n != "indicf5"]
        sticky = self._sticky.get(f"{lang}:{voice['kind']}")
        if sticky in names:
            names = [sticky] + [n for n in names if n != sticky]

        async def call(name: str) -> bytes:
            tts = self._speaker(name)
            if name == "indicf5":
                return await tts.synth(text, lang, voice, speed=speed)  # type: ignore[no-any-return]
            return await tts.synth(text, lang, voice)  # type: ignore[no-any-return]
        out = await self._run("speak", names, call)
        self._sticky.setdefault(f"{lang}:{voice['kind']}", self.used["speak"])
        return out

    async def separate(self, full_wav: Path, audio_hash: str) -> tuple[Path, Path | None]:
        """(vocals, background). Without a separation provider the full sound is the voice, with no background."""
        if not self.names("separate"):
            return full_wav, None
        from app.studio.stages import separate as sep   # tries the GPU server, then the CPU, and caches the stems

        async def call(_: str) -> tuple[Path, Path | None]:
            return await asyncio.to_thread(sep.separate, full_wav, audio_hash)
        return await self._run("separate", ["demucs"], call)

    async def diarize(self, wav: Path) -> list[dict[str, Any]]:
        """Who speaks when: [{start, end, speaker}]. An empty list means one speaker (nothing to tell apart)."""
        async def call(name: str) -> list[dict[str, Any]]:
            if name == "none":
                return []
            from app.v1.qa import QAClient
            return await QAClient(self.r.s).diarize(wav)
        return await self._run("diarize", self.names("diarize") or ["none"], call)

    async def score(self, wav: Path, text: str, lang: str, ref_wav: Path | None = None) -> dict[str, Any]:
        """How good a dubbed line is: `backcheck` (share of its words heard back, 0-1), `similarity` (its voice
        against the speaker's, when a provider measures it, else None), `heard` and `by` (who scored)."""
        async def call(name: str) -> dict[str, Any]:
            if name == "qa_server":
                from app.v1.qa import QAClient
                return {**(await QAClient(self.r.s).score(wav, text, lang, ref_wav)), "by": name}
            from app.live.pipeline import words_heard
            heard = (await self.r.provider("stt", "prisma").transcribe(str(wav), lang)).text
            return {"heard": heard, "backcheck": round(words_heard(text, heard), 3), "similarity": None, "by": name}
        return await self._run("score", self.names("score"), call)


def _stt_kw(name: str, kw: dict[str, Any]) -> dict[str, Any]:
    return kw if name != "indic_transcribe" else {}
