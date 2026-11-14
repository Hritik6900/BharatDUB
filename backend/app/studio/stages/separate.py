"""Stage 3: vocals / background split with Demucs htdemucs.

On our GPU machine when `GPU_SEPARATE_URL` is set (gpu_engine/sep_engine.py, same maths), else and on any failure
there, on this machine's CPU in a subprocess. Cached by the hash of full.wav. If both fail the caller continues
without background music.
"""
import io
import logging
import subprocess
import sys
import time
from pathlib import Path

import httpx
import soundfile as sf

from app.config import BACKEND_DIR, get_settings
from app.shared import cache

MODEL = "htdemucs"
log = logging.getLogger("studio")
last_run: dict[str, object] = {}   # where the last split ran and how long it took (for timings and tests)


def separate(full_wav: Path, audio_hash: str, timeout_s: int = 900) -> tuple[Path, Path]:
    """Return (vocals.wav, no_vocals.wav), both 44.1 kHz mono."""
    key = f"{audio_hash[:32]}-{MODEL}"
    vocals, background = cache.get_file("separate", key + "-vocals", "wav"), \
        cache.get_file("separate", key + "-bg", "wav")
    if vocals and background:
        return vocals, background
    out_v = cache.file_path("separate", key + "-vocals", "wav")
    out_b = cache.file_path("separate", key + "-bg", "wav")
    url = get_settings().gpu_separate_url
    if url:
        try:
            _separate_gpu(url, full_wav, out_v, out_b)
            return out_v, out_b
        except Exception as e:  # noqa: BLE001 - fail soft: the CPU does it
            log.warning("gpu separation failed, using the CPU: %s", e)
            for f in (out_v, out_b):
                f.unlink(missing_ok=True)
    t0 = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, "-m", "app.studio.demucs_worker", str(full_wav), str(out_v), str(out_b)],
        cwd=BACKEND_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout_s,
    )
    if proc.returncode != 0 or not out_v.exists() or not out_b.exists():
        raise RuntimeError(f"demucs failed: {proc.stderr.strip()[-600:]}")
    last_run.clear()
    last_run.update(where="cpu", total_s=round(time.perf_counter() - t0, 2))
    return out_v, out_b


def _separate_gpu(url: str, full_wav: Path, out_v: Path, out_b: Path) -> None:
    """Send the audio as FLAC (lossless, about half the bytes), get both stems back as FLAC, store them as WAV."""
    t0 = time.perf_counter()
    audio, sr = sf.read(full_wav, dtype="int16", always_2d=False)
    buf = io.BytesIO()
    sf.write(buf, audio, sr, format="FLAC", subtype="PCM_16")
    sent = buf.getvalue()
    with httpx.Client(timeout=httpx.Timeout(180.0, connect=4.0)) as c:
        r = c.post(url.rstrip("/") + "/separate", files={"audio": ("full.flac", sent, "audio/flac")})
    r.raise_for_status()
    n = int.from_bytes(r.content[:8], "big")
    if n <= 0 or 8 + n >= len(r.content):
        raise RuntimeError("gpu separation: malformed reply")
    for raw, out in ((r.content[8:8 + n], out_v), (r.content[8 + n:], out_b)):
        stem, stem_sr = sf.read(io.BytesIO(raw), dtype="int16", always_2d=False)
        if stem_sr != sr or abs(len(stem) - len(audio)) > sr // 10:
            raise RuntimeError("gpu separation: stem does not match the input")
        sf.write(out, stem, stem_sr, subtype="PCM_16")
    last_run.clear()
    last_run.update(where="gpu", total_s=round(time.perf_counter() - t0, 2),
                    gpu_s=round(float(r.headers.get("x-separate-ms", "0")) / 1000, 2),
                    sent_mb=round(len(sent) / 1e6, 2), received_mb=round(len(r.content) / 1e6, 2))
