"""Stage 8: fit a synthesized line into its slot (atempo <= 1.35x)."""
import shutil
from pathlib import Path

from app.shared import audio_utils as au

MAX_SPEED = 1.35


def slots(starts: list[float], duration: float) -> list[float]:
    """Slot for line i = start_i .. start_{i+1} (last line: to end of video)."""
    ends = starts[1:] + [duration]
    return [max(0.0, e - s) for s, e in zip(starts, ends)]


def needed_speed(clip_s: float, slot_s: float) -> float:
    if slot_s <= 0 or clip_s <= slot_s:
        return 1.0
    return clip_s / slot_s


def fit_clip(raw: Path, slot_s: float, out: Path, max_speed: float = MAX_SPEED) -> float:
    """Write the fitted clip to `out`; return the speed applied (1.0 = untouched)."""
    speed = min(needed_speed(au.duration_s(raw), slot_s), max_speed)
    if speed <= 1.001:
        shutil.copyfile(raw, out)
        return 1.0
    au.atempo(raw, out, speed)
    return round(speed, 3)
