"""Stage 9: lay dubbed lines over the background, ducking the background -6 dB under speech."""
from pathlib import Path

import numpy as np

from app.shared import audio_utils as au

DUCK_DB = -6.0
RAMP_S = 0.05


def duck_regions(placements: list[tuple[int, int]], total: int) -> list[tuple[int, int]]:
    regions = sorted((max(0, s), min(total, s + n)) for s, n in placements if n > 0)
    merged: list[list[int]] = []
    for s, e in regions:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged if e > s]


def gain_curve(total: int, regions: list[tuple[int, int]], sr: int, duck_db: float = DUCK_DB) -> np.ndarray:
    g = np.ones(total, dtype=np.float32)
    low = 10 ** (duck_db / 20)
    ramp = max(1, int(RAMP_S * sr))
    for s, e in regions:
        g[s:e] = low
        a = max(0, s - ramp)
        g[a:s] = np.minimum(g[a:s], np.linspace(1.0, low, s - a, dtype=np.float32))
        b = min(total, e + ramp)
        g[e:b] = np.minimum(g[e:b], np.linspace(low, 1.0, b - e, dtype=np.float32))
    return g


def mix(lines: list[tuple[float, Path]], background: Path | None, duration: float, out: Path,
        sr: int = au.MIX_SR) -> None:
    total = int(round(duration * sr))
    dub = np.zeros(total, dtype=np.float32)
    placements = []
    for start_s, path in lines:
        clip = au.load_mono(path, sr)
        s = int(round(start_s * sr))
        n = max(0, min(len(clip), total - s))
        dub[s:s + n] += clip[:n]
        placements.append((s, n))
    if background is not None:
        bg = au.load_mono(background, sr)
        bg = np.pad(bg, (0, max(0, total - len(bg))))[:total]
        bg = bg * gain_curve(total, duck_regions(placements, total), sr)
    else:
        bg = np.zeros(total, dtype=np.float32)
    mixed = bg + dub
    peak = float(np.max(np.abs(mixed))) if total else 0.0
    if peak > 0.98:
        mixed = mixed * (0.98 / peak)
    au.write_wav(out, mixed, sr)
