"""Provider protocols. Pipelines depend on these, never on HTTP clients directly."""
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, TypedDict


class ProviderError(RuntimeError):
    """An external AI call failed after retries. `retryable` is False for auth/credit/validation errors."""

    def __init__(self, message: str, *, status: int | None = None, retryable: bool = False) -> None:
        super().__init__(message)
        self.status = status
        self.retryable = retryable


class SpeakerEmbedding(TypedDict):
    embedding: str
    shape: list[int]
    dtype: str


class StockVoice(TypedDict):
    kind: Literal["stock"]
    voice: str


class CloneVoice(TypedDict):
    kind: Literal["clone"]
    embedding: SpeakerEmbedding


VoiceSpec = StockVoice | CloneVoice


@dataclass
class STTResult:
    text: str
    detected_lang: str | None = None
    request_id: str | None = None
    processing_time: float | None = None
    latency_s: float | None = None  # wall clock measured on our side
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class TranscriptEvent:
    """Realtime STT event. kind == "final" carries the utterance text.

    With partials on (`x-partials: true`), "partial" carries the utterance so far in `text` and the part the
    recogniser no longer changes in `stable_text`; "processing" then carries `t_ms`, the stream-clock time
    at which the end of speech was declared.
    """

    kind: Literal["connected", "speech_start", "processing", "partial", "final", "error"]
    text: str = ""
    stable_text: str = ""
    t_ms: int | None = None
    segment_id: str | None = None
    utterance_id: str | None = None
    detected_lang: str | None = None
    server_latency: float | None = None
    audio_duration_ms: int | None = None
    message: str = ""


class STT(Protocol):
    async def transcribe(self, wav_path: str, lang: str = "indic-auto", *, fmt: str | None = None,
                         keyterms: list[str] | None = None) -> STTResult: ...


class StreamingSTT(Protocol):
    def stream(self, pcm_frames: AsyncIterator[bytes], lang: str) -> AsyncIterator[TranscriptEvent]: ...


class LLM(Protocol):
    async def translate_batch(self, lines: list[str], target: str, glossary: list[str]) -> list[str]: ...

    async def translate_chunk(self, text: str, target: str, glossary: list[str], context: list[str],
                              brief: bool = False, native: bool = False) -> str: ...

    async def shorten(self, text: str, target: str, max_seconds: float) -> str: ...


class TTS(Protocol):
    async def synth(self, text: str, lang: str, voice: VoiceSpec) -> bytes: ...

    def synth_stream(self, text: str, lang: str, voice: VoiceSpec, *,
                     sample_rate: int | None = None) -> AsyncIterator[bytes]: ...

    async def clone_embedding(self, wav_path: str, *, consent_at: str | None) -> SpeakerEmbedding: ...
