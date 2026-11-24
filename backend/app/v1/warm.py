"""v1.1 session start (`V1_LIVE_WARMSTART`) and one English voice (`V1_EN_SINGLE_VOICE`): the parts without I/O.

  PitchTracker   how high the speaker's voice is, from the sound the session is fed (median F0 of voiced windows)
  pick_stock     the stock voice of a language that is nearest to that speaker (male or female, where both exist)
  fade, level    a softened change of voice: fade out, fade in, and the new voice brought towards the old level
  en_mode        which one voice English is spoken in for a whole session

A stock voice is chosen once per language and session and kept, so the estimate can never flip a voice mid-stream.
"""
from typing import Any

import numpy as np

from app.config import VOICE_BY_LANG, VOICE_BY_LANG_MALE

RATE = 16000
WINDOW = 1024            # samples: 64 ms, at least four periods of the lowest voice looked for
F0_MIN, F0_MAX = 70.0, 400.0
MIN_RMS = 300.0          # PCM16 units, the same gate the voice sample uses: quieter windows are pauses
MIN_PERIODIC = 0.55      # normalised autocorrelation at the pitch lag; under it the window is noise, breath or music
MIN_WINDOWS = 12         # voiced windows (about 0.8 s of voiced speech) before anything is said
MAX_WINDOWS = 160        # enough: after this the tracker stops listening
MALE_UNDER_HZ = 165.0    # median F0 under this: a male voice (adult men about 85-155 Hz, women about 165-255 Hz)


def f0_hz(x: np.ndarray, rate: int = RATE) -> float | None:
    """Pitch of one window by autocorrelation, or None when it is quiet or has no clear pitch."""
    x = x.astype(np.float64)
    if len(x) < WINDOW // 2 or float(np.sqrt(np.mean(x ** 2))) < MIN_RMS:
        return None
    x = x - x.mean()
    lo, hi = int(rate / F0_MAX), min(int(rate / F0_MIN), len(x) - 1)
    ac = np.correlate(x, x, "full")[len(x) - 1:]
    if ac[0] <= 0 or hi <= lo:
        return None
    # Each lag is judged on the samples that overlap, so a long lag is not marked down for having fewer of them.
    norm = ac[lo:hi + 1] / (ac[0] * (1 - np.arange(lo, hi + 1) / len(x)))
    k = int(np.argmax(norm))
    if norm[k] < MIN_PERIODIC:
        return None
    # A voice at 110 Hz is as periodic at 55 Hz: the shortest lag that is nearly as good is the pitch.
    for j in range(k):
        if norm[j] >= 0.9 * norm[k] and (j == 0 or norm[j] >= norm[j - 1]) and norm[j] >= norm[j + 1]:
            k = j
            break
    return rate / (lo + k)


class PitchTracker:
    """Fed the session's 16 kHz PCM16 frames; knows the speaker's median pitch after about a second of speech."""

    def __init__(self) -> None:
        self._buf = b""
        self.f0s: list[float] = []

    @property
    def done(self) -> bool:
        return len(self.f0s) >= MAX_WINDOWS

    def add(self, pcm: bytes) -> None:
        if self.done:
            return
        self._buf += pcm
        size = WINDOW * 2
        while len(self._buf) >= size:
            win, self._buf = self._buf[:size], self._buf[size:]
            f0 = f0_hz(np.frombuffer(win, dtype="<i2"))
            if f0 is not None:
                self.f0s.append(f0)

    def median_hz(self) -> float | None:
        return float(np.median(self.f0s)) if len(self.f0s) >= MIN_WINDOWS else None

    def gender(self) -> str | None:
        """"male" / "female" by the median pitch, None while too little voiced speech was heard."""
        f0 = self.median_hz()
        return None if f0 is None else "male" if f0 < MALE_UNDER_HZ else "female"


def pick_stock(lang: str, gender: str | None) -> dict[str, Any]:
    """The stock voice for `lang` nearest to the speaker: {voice, matched, note}. `matched` is False when the
    speaker's pitch is not known yet, or the language has no voice of that gender (then `note` says so)."""
    default = VOICE_BY_LANG.get(lang, VOICE_BY_LANG["hi-IN"])
    if gender is None:
        return {"voice": default, "matched": False, "note": "the speaker's pitch was not known yet"}
    if gender == "female":
        return {"voice": default, "matched": True, "note": ""}
    male = VOICE_BY_LANG_MALE.get(lang)
    if male:
        return {"voice": male, "matched": True, "note": ""}
    return {"voice": default, "matched": False, "note": "this language has female stock voices only"}


def fade(pcm: bytes, rate: int, ms: int, *, out: bool) -> bytes:
    """PCM16 mono with its last (`out`) or first `ms` faded on an equal-power curve."""
    x = np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype="<i2").astype(np.float32)
    n = min(len(x), int(rate * ms / 1000))
    if n < 2:
        return pcm
    ramp = np.sin(np.linspace(0.0, np.pi / 2, n, dtype=np.float32))
    if out:
        x[-n:] *= ramp[::-1]
    else:
        x[:n] *= ramp
    return x.astype("<i2").tobytes()


def level(pcm: bytes) -> float:
    """RMS of the sound that is not silence (PCM16 units), 0 when there is none."""
    x = np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype="<i2").astype(np.float64)
    loud = x[np.abs(x) > 200]
    return float(np.sqrt(np.mean(loud ** 2))) if len(loud) > 100 else 0.0


def toward(pcm: bytes, own: float, other: float, share: float, max_db: float = 6.0) -> bytes:
    """`pcm` (level `own`) moved `share` of the way (in dB) to the level `other`, by at most `max_db`, never clipped."""
    if own <= 0 or other <= 0 or share <= 0:
        return pcm
    db = float(np.clip(20 * np.log10(other / own) * share, -max_db, max_db))
    x = np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype="<i2").astype(np.float32) * 10 ** (db / 20)
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    if peak > 32000:
        x *= 32000 / peak
    return x.astype("<i2").tobytes()


def en_mode(setting: str) -> str:
    """`V1_EN_SINGLE_VOICE`: "copy" or "stock" for the whole session. `auto` is the measured choice, today the
    stock voice: with every English line in the hosted copy, 73.7% of the lines started within 1 s of their moment
    against 87.2% in the stock voice (dense reel, 3 runs each, 25 Nov 2026; docs/v1/PROGRESS.md, v1.1 WS2), and
    a copy that is learned from the stream is not there for a session's first lines at all. `copy` is for whoever
    prefers the speaker's voice to the timing."""
    return "copy" if setting == "copy" else "stock"
