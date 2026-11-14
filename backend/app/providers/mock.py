"""Simulated providers for UI work without keys (MOCK_PROVIDERS=true). The UI shows a "mock mode" banner.

Speech-to-text returns sample Hinglish lines; streaming STT detects speech by loudness on the real mic
audio. Translation uses a small hand-written phrasebook. TTS produces syllable-like tones, not speech.
"""
import asyncio
import io
import itertools
import json
import math
import time
from collections.abc import AsyncIterator
from pathlib import Path

import numpy as np
import soundfile as sf

from app.providers.base import SpeakerEmbedding, STTResult, TranscriptEvent, VoiceSpec

LINES = [
    "Doston, aaj hum ranked match khelenge.",
    "Bhai ye clutch moment tha, full send!",
    "Chat mein batao, next kaunsa map khelein?",
    "Like aur subscribe karna mat bhoolna.",
    "Ek aur round, phir break lete hain.",
    "GG doston, aaj ka stream mast tha.",
]
PHRASEBOOK: dict[str, list[str]] = {
    "en-IN": ["Friends, today we're playing a ranked match.", "Bro, that was a clutch moment, full send!",
              "Tell me in chat, which map should we play next?", "Don't forget to like and subscribe.",
              "One more round, then we take a break.", "GG friends, today's stream was awesome."],
    "ta-IN": ["நண்பர்களே, இன்னைக்கு நாம ranked match விளையாடப் போறோம்.", "ப்ரோ, இது clutch moment, full send!",
              "Chat-ல சொல்லுங்க, அடுத்து எந்த map விளையாடலாம்?", "Like, subscribe பண்ண மறக்காதீங்க.",
              "இன்னும் ஒரு round, அப்புறம் break எடுக்கலாம்.", "GG நண்பர்களே, இன்னைக்கு stream செம்மையா இருந்துச்சு."],
    "bn-IN": ["বন্ধুরা, আজ আমরা ranked match খেলব।", "ভাই, এটা clutch moment ছিল, full send!",
              "Chat-এ বলো, এরপর কোন map খেলব?", "Like আর subscribe করতে ভুলো না।",
              "আর এক round, তারপর break নেব।", "GG বন্ধুরা, আজকের stream দারুণ ছিল।"],
    "te-IN": ["ఫ్రెండ్స్, ఈరోజు మనం ranked match ఆడబోతున్నాం.", "బ్రో, ఇది clutch moment, full send!",
              "Chat లో చెప్పండి, తర్వాత ఏ map ఆడదాం?", "Like, subscribe చేయడం మర్చిపోకండి.",
              "ఇంకో round, తర్వాత break తీసుకుందాం.", "GG ఫ్రెండ్స్, ఈరోజు stream అదిరిపోయింది."],
    "hi-IN": ["दोस्तों, आज हम ranked match खेलेंगे।", "भाई ये clutch moment था, full send!",
              "Chat में बताओ, next कौनसा map खेलें?", "Like और subscribe करना मत भूलना।",
              "एक और round, फिर break लेते हैं।", "GG दोस्तों, आज का stream मस्त था।"],
}
SEC_PER_CHAR = 0.065


def _translate(text: str, target: str) -> str:
    if text in LINES and target in PHRASEBOOK:
        return PHRASEBOOK[target][LINES.index(text)]
    return text  # outside the phrasebook the mock passes text through untranslated


def _tone(text: str, sr: int) -> np.ndarray:
    """Syllable-like bursts so the player and meters have something audible."""
    n_syll = max(2, int(len(text) / 3))
    syll = int(sr * len(text) * SEC_PER_CHAR / n_syll)
    out = []
    for i in range(n_syll):
        f = 170 + 60 * math.sin(i * 1.7) + 25 * (i % 3)
        t = np.arange(syll) / sr
        env = np.sin(np.pi * np.arange(syll) / syll) ** 2
        out.append(0.25 * env * (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t)))
    return np.concatenate(out).astype(np.float32)


class MockSTT:
    def __init__(self) -> None:
        self._cycle = itertools.cycle(LINES)

    async def transcribe(self, wav_path: str, lang: str = "indic-auto", *, fmt=None, keyterms=None) -> STTResult:
        await asyncio.sleep(0.25)
        idx = int(Path(wav_path).stem.split("_")[-1]) if Path(wav_path).stem.split("_")[-1].isdigit() else 0
        return STTResult(text=LINES[idx % len(LINES)], detected_lang="hi-IN", latency_s=0.25)

    async def stream(self, pcm_frames: AsyncIterator[bytes], lang: str = "indic-auto", *,
                     sample_rate: int = 16000, pace: bool = False,
                     extra_headers: dict[str, str] | None = None) -> AsyncIterator[TranscriptEvent]:
        """Energy VAD on the real incoming audio; each utterance becomes the next sample line."""
        yield TranscriptEvent(kind="connected")
        speaking, speech_ms, silence_ms = False, 0.0, 0.0
        async for chunk in pcm_frames:
            if len(chunk) < 2:
                continue
            x = np.frombuffer(chunk[: len(chunk) // 2 * 2], dtype="<i2").astype(np.float32) / 32768
            ms = 1000 * len(x) / sample_rate
            loud = float(np.sqrt(np.mean(x ** 2))) > 0.02
            if loud:
                if not speaking:
                    speaking, speech_ms = True, 0.0
                    yield TranscriptEvent(kind="speech_start")
                speech_ms += ms
                silence_ms = 0.0
            elif speaking:
                silence_ms += ms
                if silence_ms >= 500:
                    speaking = False
                    if speech_ms >= 300:
                        yield TranscriptEvent(kind="processing")
                        await asyncio.sleep(0.3)
                        yield TranscriptEvent(kind="final", text=next(self._cycle), detected_lang="hi-IN",
                                              audio_duration_ms=int(speech_ms))


class MockLLM:
    async def translate_batch(self, lines: list[str], target: str, glossary: list[str]) -> list[str]:
        await asyncio.sleep(0.4)
        return [_translate(x, target) for x in lines]

    async def translate_chunk(self, text: str, target: str, glossary: list[str], context: list[str],
                              brief: bool = False) -> str:
        await asyncio.sleep(0.35)
        return _translate(text, target)

    async def shorten(self, text: str, target: str, max_seconds: float) -> str:
        return text[: max(8, int(max_seconds / SEC_PER_CHAR))]


class MockTTS:
    def __init__(self, sample_rate: int = 44100) -> None:
        self.sr = sample_rate
        self.last_first_chunk_s: float | None = None

    async def synth(self, text: str, lang: str, voice: VoiceSpec) -> bytes:
        await asyncio.sleep(0.3)
        buf = io.BytesIO()
        sf.write(buf, _tone(text, self.sr), self.sr, format="WAV", subtype="PCM_16")
        return buf.getvalue()

    async def synth_stream(self, text: str, lang: str, voice: VoiceSpec, *,
                           sample_rate: int | None = None, speed: float = 1.0) -> AsyncIterator[bytes]:
        sr = sample_rate or self.sr
        t0 = time.perf_counter()
        await asyncio.sleep(0.25)
        pcm = (np.clip(_tone(text, sr), -1, 1) * 32767).astype("<i2").tobytes()
        step = int(sr * 0.2) * 2
        for i in range(0, len(pcm), step):
            if i == 0:
                self.last_first_chunk_s = time.perf_counter() - t0
            yield pcm[i:i + step]
            await asyncio.sleep(0.05)

    async def clone_embedding(self, wav_path: str, *, consent_at: str | None) -> SpeakerEmbedding:
        from app.providers.tts_gnani import ConsentRequired

        if not consent_at:
            raise ConsentRequired("voice cloning requires a voice profile with consent_at set", status=403)
        await asyncio.sleep(0.5)
        return {"embedding": json.dumps("mock"), "shape": [1, 768], "dtype": "torch.bfloat16"}
