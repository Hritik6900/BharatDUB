"""Config-driven provider router (`V1_ROUTER`): which provider does which step, per mode and engine, with its
fallbacks and timeouts, read from `config/routing.yaml`.

Two things are built from the file:
  * the provider objects the pipelines already use (speech-to-text, translation, voice, copied voice), composed
    the way `providers/__init__.py` composes them, so the shipped file gives exactly what v0 gives;
  * the ordered provider names per step for `app/v1/stages.py`, which runs a step with a timeout and moves on to
    the next provider when one fails, logging why.

A provider whose address or key is missing is left out of a chain, so listing a server that does not exist yet
is harmless.
"""
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.config import BACKEND_DIR, Settings, get_settings
from app.v1 import mode as v1mode

log = logging.getLogger("bharatdub.router")

MODES = ("live", "studio", "studio_hq")
ENGINES = ("cloud", "gpu")
KNOWN: dict[str, tuple[str, ...]] = {
    "transcribe": ("prisma", "whisper_gpu", "indic_transcribe"),
    "translate": ("gemini", "gemma", "big_llm"),
    "review": ("gemini", "gemma", "big_llm"),
    "speak": ("timbre", "indicf5"),
    "copied_voice": ("indicf5", "indicf5_v1", "maya"),
    "candidates": ("maya", "indicf5_v1", "indicf5"),
    "separate": ("demucs_gpu", "demucs_cpu"),
    "diarize": ("qa_server", "none"),
    "score": ("qa_server", "prisma"),
}
DEFAULT_TIMEOUTS = {"transcribe": 30.0, "translate": 20.0, "review": 60.0, "speak": 20.0, "copied_voice": 20.0,
                    "candidates": 30.0, "separate": 180.0, "diarize": 180.0, "score": 40.0}
LOCAL_LLMS = ("gemma", "big_llm")


class RoutingError(ValueError):
    pass


def default_path() -> Path:
    s = get_settings()
    return Path(s.v1_routing_file) if s.v1_routing_file else BACKEND_DIR / "config" / "routing.yaml"


def load_config(path: Path | None = None) -> dict[str, Any]:
    path = path or default_path()
    try:
        cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise RoutingError(f"routing file {path}: {e}") from e
    validate(cfg)
    return cfg  # type: ignore[no-any-return]


def validate(cfg: Any) -> None:
    if not isinstance(cfg, dict) or not isinstance(cfg.get("modes"), dict):
        raise RoutingError("routing file: a `modes` mapping is required")
    for stage, secs in (cfg.get("timeouts_s") or {}).items():
        if stage not in KNOWN or not isinstance(secs, (int, float)) or secs <= 0:
            raise RoutingError(f"routing file: bad timeout for {stage!r}")
    for mode, engines in cfg["modes"].items():
        if mode not in MODES or not isinstance(engines, dict):
            raise RoutingError(f"routing file: unknown mode {mode!r}")
        for engine, stages in engines.items():
            if engine not in ENGINES or not isinstance(stages, dict):
                raise RoutingError(f"routing file: unknown engine {engine!r} in mode {mode}")
            for stage, names in stages.items():
                if stage not in KNOWN:
                    raise RoutingError(f"routing file: unknown step {stage!r} in {mode}.{engine}")
                if not isinstance(names, list) or not names:
                    raise RoutingError(f"routing file: {mode}.{engine}.{stage} must be a list of providers")
                bad = [n for n in names if n not in KNOWN[stage]]
                if bad:
                    raise RoutingError(f"routing file: {mode}.{engine}.{stage}: unknown provider {bad[0]!r} "
                                       f"(known: {', '.join(KNOWN[stage])})")


class Router:
    def __init__(self, cfg: dict[str, Any] | None = None, settings: Settings | None = None) -> None:
        self.s = settings or get_settings()
        self.cfg = cfg if cfg is not None else load_config()
        validate(self.cfg)
        self._objs: dict[tuple[Any, ...], Any] = {}

    # ---------- what is there ----------
    def available(self, name: str) -> bool:
        """The provider is configured (an address or a key is set). Whether it answers is found out by calling it."""
        s = self.s
        return {
            "prisma": bool(s.gnani_api_key.get_secret_value()), "timbre": bool(s.gnani_api_key.get_secret_value()),
            "whisper_gpu": bool(s.gpu_stt_url), "indic_transcribe": bool(s.v1_transcribe_url),
            "gemini": bool(s.llm_base_url and s.llm_model), "gemma": bool(s.gpu_llm_url),
            "big_llm": bool(s.v1_big_llm_url),
            "indicf5": bool(s.gpu_voice_url), "indicf5_v1": bool(s.v1_tts_server_url),
            "maya": bool(s.v1_maya_url and v1mode.on("tts_maya", s)),
            "demucs_gpu": bool(s.gpu_separate_url), "demucs_cpu": bool(s.studio_separate),
            "qa_server": bool(s.v1_qa_url), "none": True,
        }.get(name, False)

    def configured(self, mode: str, engine: str, stage: str) -> list[str]:
        """The provider names as written in the file (the copied-voice server swapped in when its flag is on)."""
        try:
            names = list(self.cfg["modes"][mode][engine].get(stage) or [])
        except KeyError:
            names = []
        if v1mode.on("tts_server", self.s) and self.s.v1_tts_server_url and stage in ("copied_voice", "candidates"):
            names = list(dict.fromkeys("indicf5_v1" if n == "indicf5" else n for n in names))
        return names

    def chain(self, mode: str, engine: str, stage: str) -> list[str]:
        """The providers of a step that are configured, in order."""
        return [n for n in self.configured(mode, engine, stage) if self.available(n)]

    def timeout(self, stage: str) -> float:
        return float((self.cfg.get("timeouts_s") or {}).get(stage, DEFAULT_TIMEOUTS.get(stage, 30.0)))

    def describe(self) -> dict[str, Any]:
        """Per mode, engine and step: what the file says and what is in use now."""
        out: dict[str, Any] = {}
        for mode in self.cfg["modes"]:
            for engine in self.cfg["modes"][mode]:
                for stage in self.cfg["modes"][mode][engine]:
                    out.setdefault(mode, {}).setdefault(engine, {})[stage] = {
                        "configured": self.configured(mode, engine, stage), "available": self.chain(mode, engine, stage),
                        "timeout_s": self.timeout(stage)}
        return out

    # ---------- single providers ----------
    def _one(self, kind: str, name: str) -> Any:
        key = ("one", kind, name)
        if key not in self._objs:
            self._objs[key] = self._make(kind, name)
        return self._objs[key]

    def _make(self, kind: str, name: str) -> Any:
        from app.providers import _guard   # `V1_BREAKER`: our own endpoints get a circuit breaker; off = untouched
        return _guard(name, self._build(kind, name))

    def _build(self, kind: str, name: str) -> Any:
        s = self.s
        if kind == "stt":
            if name == "prisma":
                from app.providers.stt_gnani import GnaniSTT
                return GnaniSTT()
            if name == "whisper_gpu":
                from app.providers.stt_gpu import GpuSTT
                return GpuSTT(s, backup=None)
            if name == "indic_transcribe":
                from app.providers.stt_indic import IndicTranscribeSTT
                return IndicTranscribeSTT(s)
        if kind == "llm":
            if name == "gemini":
                from app.providers.llm_openai import OpenAILLM
                return OpenAILLM()
            if name == "gemma":
                from app.providers import _local_llm
                return _local_llm()
            if name == "big_llm":
                from pydantic import SecretStr

                from app.providers.llm_local import LocalLLM
                return LocalLLM(s.model_copy(update={
                    "llm_base_url": s.v1_big_llm_url, "llm_model": s.v1_big_llm_model, "llm_model_fast": "",
                    "llm_api_key": SecretStr("local"), "llm_reasoning_effort": "", "llm_reasoning_effort_fast": ""}))
        if kind == "voice":
            if name == "indicf5":
                from app.providers.tts_gpu import GpuVoice
                return GpuVoice(s)
            if name == "indicf5_v1":
                from app.providers.tts_gpu_v1 import IndicF5V1Voice
                return IndicF5V1Voice(s)
            if name == "maya":
                from app.providers.tts_gpu_v1 import MayaVoice
                return MayaVoice(s)
        if kind == "tts" and name == "timbre":
            from app.providers.tts_gnani import GnaniTTS
            return GnaniTTS()
        raise RoutingError(f"no {kind} provider called {name!r}")

    def provider(self, kind: str, name: str) -> Any:
        """One provider by name, for a caller that wants a particular one (the steps in stages.py)."""
        return self._one(kind, name)

    # ---------- what the pipelines ask for ----------
    def stt(self, mode: str, engine: str) -> Any:
        names = self.chain(mode, engine, "transcribe")
        if mode != "studio_hq":
            names = [n for n in names if n != "indic_transcribe"] or names   # not a streaming model
        names = names or self.configured(mode, engine, "transcribe")[:1] or ["prisma"]
        key = ("stt", tuple(names))
        if key not in self._objs:
            self._objs[key] = self._stt_chain(names)
        return self._objs[key]

    def _stt_chain(self, names: list[str]) -> Any:
        if len(names) == 1:
            return self._one("stt", names[0])
        rest = self._stt_chain(names[1:])
        if names[0] == "whisper_gpu":
            # Our model first: its own client carries the fallback and goes back to the engine once it answers again.
            from app.providers import _guard
            from app.providers.stt_gpu import GpuSTT
            return _guard("whisper_gpu", GpuSTT(self.s, backup=rest))
        from app.providers.fallback import FallbackSTT
        return FallbackSTT(self._one("stt", names[0]), rest)

    def llm(self, mode: str, engine: str, stage: str = "translate") -> Any:
        names = self.chain(mode, engine, stage) or self.configured(mode, engine, stage)[:1] or ["gemini"]
        key = ("llm", tuple(names))
        if key not in self._objs:
            self._objs[key] = self._llm_chain(names)
        return self._objs[key]

    def _llm_chain(self, names: list[str]) -> Any:
        first = self._one("llm", names[0])
        if len(names) == 1 and names[0] not in LOCAL_LLMS:
            return first
        from app.providers.fallback import FallbackLLM
        return FallbackLLM(first, self._llm_chain(names[1:]) if len(names) > 1 else None)

    def gpu_voice(self, mode: str, engine: str) -> Any:
        names = self.chain(mode, engine, "copied_voice")
        key = ("gpu_voice", tuple(names[:1]), engine)
        if key in self._objs:
            return self._objs[key]
        s = self.s
        if not names:
            from app.providers.tts_gpu import GpuVoice
            gpu: Any = GpuVoice(s.model_copy(update={"gpu_voice_url": ""}))   # as v0 without an engine: disabled
        else:
            gpu = self._make("voice", names[0])
        if engine == "gpu":
            from app.providers import _local_llm
            gpu.ref_text_fix = _local_llm().to_devanagari
            if s.gpu_voice_guard and gpu.enabled:
                from app.providers.tts_gpu_guard import GuardedVoice
                from app.providers.tts_gpu_mio import MioVoice
                from app.providers import _guard
                gpu = GuardedVoice(gpu, _guard("mio", MioVoice(s)) if s.gpu_mio_url else None, s)
        self._objs[key] = gpu
        return gpu

    def tts(self, mode: str, engine: str) -> Any:
        names = self.chain(mode, engine, "speak")
        voice_there = bool(self.chain(mode, engine, "copied_voice"))
        own = "indicf5" in self.configured(mode, engine, "speak") and voice_there
        key = ("tts", own, "timbre" in names, tuple(self.chain(mode, engine, "transcribe")) if own else (),
               engine if own else "")
        if key in self._objs:
            return self._objs[key]
        hosted = self._one("tts", "timbre")
        if own:
            from app.providers.tts_gpu_studio import GpuStudioTTS
            obj: Any = GpuStudioTTS(self.gpu_voice(mode, engine), self.stt(mode, engine), self.s,
                                    backup=hosted if "timbre" in names else None)
        else:
            obj = hosted
        self._objs[key] = obj
        return obj


@lru_cache
def get_router() -> Router:
    return Router()


def active() -> Router | None:
    """The router when it is switched on (and the providers are not mocked), else None: v0's fixed table is used."""
    s = get_settings()
    if not v1mode.on("router", s) or s.mock_providers:
        return None
    try:
        return get_router()
    except RoutingError as e:   # a broken file must not take the service down: v0's table answers
        log.error("router off, the fixed provider table is used: %s", e)
        return None
