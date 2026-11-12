"""Stage 4: speech segments via Silero VAD, merged at short gaps, each <= 25 s (Prisma REST max is 30 s)."""
from pathlib import Path

import numpy as np

from app.shared import audio_utils as au

MAX_LEN = 25.0
MIN_GAP = 0.35
MIN_SEG = 0.3
FALLBACK_WINDOW = 20.0


def merge_segments(ts: list[tuple[float, float]], max_len: float = MAX_LEN, min_gap: float = MIN_GAP,
                   min_seg: float = MIN_SEG) -> list[tuple[float, float]]:
    merged: list[list[float]] = []
    for s, e in ts:
        if merged and s - merged[-1][1] < min_gap and e - merged[-1][0] <= max_len:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    out: list[tuple[float, float]] = []
    for s, e in merged:
        while e - s > max_len:
            out.append((round(s, 3), round(s + max_len, 3)))
            s += max_len
        if e - s >= min_seg:
            out.append((round(s, 3), round(e, 3)))
    return out


def fixed_windows(duration: float, window: float = FALLBACK_WINDOW) -> list[tuple[float, float]]:
    out, s = [], 0.0
    while s < duration - 0.05:
        out.append((round(s, 3), round(min(duration, s + window), 3)))
        s += window
    return out


def vad(audio16k: np.ndarray) -> list[tuple[float, float]]:
    import torch
    from silero_vad import get_speech_timestamps, load_silero_vad

    model = load_silero_vad()
    ts = get_speech_timestamps(torch.from_numpy(audio16k.astype(np.float32)), model,
                               sampling_rate=16000, return_seconds=True)
    return [(float(t["start"]), float(t["end"])) for t in ts]


def segment(vocals16k_wav: Path) -> list[tuple[float, float]]:
    return merge_segments(vad(au.load_mono(vocals16k_wav, 16000)))
