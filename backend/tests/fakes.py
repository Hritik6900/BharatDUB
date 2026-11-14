"""Fake providers for pipeline tests: deterministic, offline, and they count calls."""
import io
from pathlib import Path

import numpy as np
import soundfile as sf

from app.providers.base import STTResult, VoiceSpec

SECONDS_PER_CHAR = 0.06


class FakeSTT:
    def __init__(self) -> None:
        self.calls = 0

    async def transcribe(self, wav_path: str, lang: str = "indic-auto", *, fmt=None, keyterms=None) -> STTResult:
        self.calls += 1
        return STTResult(text=f"namaste line {Path(wav_path).stem}", detected_lang="hi-IN")


class FakeLLM:
    def __init__(self) -> None:
        self.batch_calls = 0
        self.shorten_calls = 0

    async def translate_batch(self, lines, target, glossary):
        self.batch_calls += 1
        return [f"{target} {line}" for line in lines]

    async def translate_chunk(self, text, target, glossary, context, brief=False, native=False):
        return f"{target} {text}"

    async def shorten(self, text, target, max_seconds):
        self.shorten_calls += 1
        return text[: max(4, int(max_seconds / SECONDS_PER_CHAR) - 2)]


class FakeTTS:
    def __init__(self) -> None:
        self.calls = 0
        self.texts: list[str] = []

    async def synth(self, text: str, lang: str, voice: VoiceSpec) -> bytes:
        self.calls += 1
        self.texts.append(text)
        sr = 44100
        n = int(sr * SECONDS_PER_CHAR * len(text))
        tone = 0.3 * np.sin(2 * np.pi * 220 * np.arange(n) / sr).astype(np.float32)
        buf = io.BytesIO()
        sf.write(buf, tone, sr, format="WAV", subtype="PCM_16")
        return buf.getvalue()

    async def synth_stream(self, text, lang, voice):
        yield await self.synth(text, lang, voice)

    async def clone_embedding(self, wav_path, *, consent_at):
        return {"embedding": "x", "shape": [1, 768], "dtype": "torch.bfloat16"}
