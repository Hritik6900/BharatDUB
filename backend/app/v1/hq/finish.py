"""Studio HQ, finish: the mix. Two differences from v0's mix:

  * sidechain ducking: the background follows the dubbed voice's own loudness, going down while it speaks and
    coming back in the gaps between words and lines, instead of a fixed -6 dB over each whole line;
  * loudness: the finished mix is brought to one loudness (`v1_hq_loudness_lufs`), so every video and language
    comes out at the same level.
"""
import shutil
from pathlib import Path

import numpy as np

from app.shared import audio_utils as au

WINDOW_S, ATTACK_S, RELEASE_S = 0.02, 0.03, 0.25
OPEN_DB, FULL_DB = -45.0, -25.0    # voice level at which the background starts to go down / is fully down


def envelope(x: np.ndarray, sr: int) -> np.ndarray:
    """How loud the voice is at each sample (0-1): RMS in short windows, fast to rise, slow to fall."""
    win = max(1, int(WINDOW_S * sr))
    n = len(x) // win
    if n == 0:
        return np.zeros(len(x), dtype=np.float32)
    rms = np.sqrt(np.mean(x[: n * win].reshape(n, win).astype(np.float64) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms + 1e-9)
    level = np.clip((db - OPEN_DB) / (FULL_DB - OPEN_DB), 0.0, 1.0)
    up, down = 1 - np.exp(-WINDOW_S / ATTACK_S), 1 - np.exp(-WINDOW_S / RELEASE_S)
    out = np.empty(n)
    cur = 0.0
    for i, v in enumerate(level):
        cur += (v - cur) * (up if v > cur else down)
        out[i] = cur
    full = np.repeat(out, win)
    return np.pad(full, (0, len(x) - len(full)), mode="edge").astype(np.float32)


def sidechain_gain(dub: np.ndarray, sr: int, duck_db: float) -> np.ndarray:
    """Gain for the background at each sample: 1 in silence, `duck_db` under full voice."""
    low = 10 ** (duck_db / 20)
    return (1.0 - (1.0 - low) * envelope(dub, sr)).astype(np.float32)


def mix(lines: list[tuple[float, Path]], background: Path | None, duration: float, out: Path, *,
        duck_db: float = -9.0, sr: int = au.MIX_SR) -> None:
    total = int(round(duration * sr))
    dub = np.zeros(total, dtype=np.float32)
    for start_s, path in lines:
        clip = au.load_mono(path, sr)
        s = int(round(start_s * sr))
        n = max(0, min(len(clip), total - s))
        dub[s:s + n] += clip[:n]
    if background is not None:
        bg = au.load_mono(background, sr)
        bg = np.pad(bg, (0, max(0, total - len(bg))))[:total] * sidechain_gain(dub, sr, duck_db)
    else:
        bg = np.zeros(total, dtype=np.float32)
    mixed = bg + dub
    peak = float(np.max(np.abs(mixed))) if total else 0.0
    if peak > 0.98:
        mixed = mixed * (0.98 / peak)
    au.write_wav(out, mixed, sr)


def loudness(path: Path, lufs: float) -> bool:
    """Bring the file to `lufs` integrated loudness in place (ffmpeg `loudnorm`). False = left as it was."""
    if not lufs:
        return False
    tmp = path.with_suffix(".norm.wav")
    try:
        au.run([au.ffmpeg_bin(), "-y", "-i", str(path), "-af", f"loudnorm=I={lufs}:TP=-1.5:LRA=11",
                "-ar", str(au.MIX_SR), "-ac", "1", str(tmp)], what="loudness")
        shutil.move(str(tmp), str(path))
        return True
    except (au.FFmpegError, OSError):
        tmp.unlink(missing_ok=True)
        return False
