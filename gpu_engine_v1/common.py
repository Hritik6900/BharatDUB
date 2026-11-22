"""Shared by the v1 model servers: settings from the environment, the stub voice, audio encoding.

Stub mode (`V1_STUB=1`): a server starts without its model and answers with made-up but well-formed results (a tone
as long as the text would take to say, the text itself as a transcript). It needs no GPU, so the calls, the health
check and the backend's handling of each server can be tested before the real model is allowed onto the card.
"""
import io
import os

import numpy as np
import soundfile as sf

STUB = os.environ.get("V1_STUB", "0") == "1"
SR = 24000


def env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def letters(text: str) -> int:
    return max(1, sum(1 for ch in text if not ch.isspace()))


def stub_wave(text: str, speed: float = 1.0, sr: int = SR, ms_per_letter: float = 70.0) -> np.ndarray:
    """A quiet tone with the length a voice would need for `text`; silence between the words."""
    out: list[np.ndarray] = []
    for word in text.split():
        n = int(sr * letters(word) * ms_per_letter / 1000 / max(0.4, speed))
        t = np.arange(n) / sr
        out += [0.2 * np.sin(2 * np.pi * 180 * t).astype(np.float32), np.zeros(int(sr * 0.04), dtype=np.float32)]
    return np.concatenate(out) if out else np.zeros(int(sr * 0.2), dtype=np.float32)


def encode(wave: np.ndarray, fmt: str, sr: int = SR) -> bytes:
    """PCM16 mono as raw bytes, MP3 (about a tenth of the size, quick to make) or Opus."""
    peak = float(np.max(np.abs(wave))) if wave.size else 0.0
    if peak > 0.98:
        wave = wave * (0.98 / peak)
    pcm = (wave * 32767.0).astype("<i2")
    if fmt == "pcm":
        return pcm.tobytes()
    buf = io.BytesIO()
    if fmt == "mp3":
        sf.write(buf, pcm, sr, format="MP3", subtype="MPEG_LAYER_III", compression_level=0.7, bitrate_mode="VARIABLE")
    else:
        sf.write(buf, pcm, sr, format="OGG", subtype="OPUS")
    return buf.getvalue()


def read_mono(raw: bytes, sr: int = 16000) -> np.ndarray:
    """Any audio file libsndfile reads -> float32 mono at `sr` (linear resampling; enough for speech models)."""
    x, rate = sf.read(io.BytesIO(raw), dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    if rate != sr and len(x):
        n = int(len(x) * sr / rate)
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
    return x
