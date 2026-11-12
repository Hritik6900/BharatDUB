"""Stage 3: vocals / background split with Demucs htdemucs (CPU). Runs in a subprocess.

Cached by the hash of full.wav. On failure the caller continues without background music.
"""
import subprocess
import sys
from pathlib import Path

from app.config import BACKEND_DIR
from app.shared import cache

MODEL = "htdemucs"


def separate(full_wav: Path, audio_hash: str, timeout_s: int = 900) -> tuple[Path, Path]:
    """Return (vocals.wav, no_vocals.wav), both 44.1 kHz mono."""
    key = f"{audio_hash[:32]}-{MODEL}"
    vocals, background = cache.get_file("separate", key + "-vocals", "wav"), \
        cache.get_file("separate", key + "-bg", "wav")
    if vocals and background:
        return vocals, background
    out_v = cache.file_path("separate", key + "-vocals", "wav")
    out_b = cache.file_path("separate", key + "-bg", "wav")
    proc = subprocess.run(
        [sys.executable, "-m", "app.studio.demucs_worker", str(full_wav), str(out_v), str(out_b)],
        cwd=BACKEND_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout_s,
    )
    if proc.returncode != 0 or not out_v.exists() or not out_b.exists():
        raise RuntimeError(f"demucs failed: {proc.stderr.strip()[-600:]}")
    return out_v, out_b
