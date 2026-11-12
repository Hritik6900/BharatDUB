"""ffmpeg + numpy audio helpers. All audio in the pipeline is mono float32 at a known sample rate."""
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

MIX_SR = 44100


class FFmpegError(RuntimeError):
    pass


def _find(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    # winget installs may not be on PATH in an already-open shell.
    winget = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet"
    links = winget / "Links" / f"{name}.exe"
    if links.exists():
        return str(links)
    for p in sorted(winget.glob(f"Packages/*FFmpeg*/*/bin/{name}.exe"), reverse=True):
        return str(p)
    raise FFmpegError(f"{name} not found on PATH (set FFMPEG_BIN / FFPROBE_BIN)")


def ffmpeg_bin() -> str:
    return os.environ.get("FFMPEG_BIN") or _find("ffmpeg")


def ffprobe_bin() -> str:
    return os.environ.get("FFPROBE_BIN") or _find("ffprobe")


def run(cmd: list[str], *, what: str) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise FFmpegError(f"{what} failed: {proc.stderr.strip()[-800:]}")


def probe(path: str | Path) -> dict:
    proc = subprocess.run(
        [ffprobe_bin(), "-v", "error", "-show_entries", "format=duration:stream=codec_type",
         "-of", "json", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        raise FFmpegError(f"ffprobe failed: {proc.stderr.strip()[-400:]}")
    j = json.loads(proc.stdout or "{}")
    kinds = [s.get("codec_type") for s in j.get("streams", [])]
    return {"duration": float(j.get("format", {}).get("duration") or 0.0),
            "has_video": "video" in kinds, "has_audio": "audio" in kinds}


def extract_wav(src: str | Path, out: str | Path, sr: int = MIX_SR) -> None:
    run([ffmpeg_bin(), "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", str(sr), str(out)],
        what="extract audio")


def load_mono(path: str | Path, sr: int = MIX_SR) -> np.ndarray:
    """Read any WAV as mono float32 at `sr` (resamples through ffmpeg if needed)."""
    data, file_sr = sf.read(str(path), dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    if file_sr == sr:
        return mono
    tmp = Path(path).with_suffix(f".{sr}.wav")
    run([ffmpeg_bin(), "-y", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr), str(tmp)],
        what="resample")
    out, _ = sf.read(str(tmp), dtype="float32")
    tmp.unlink(missing_ok=True)
    return out


def write_wav(path: str | Path, audio: np.ndarray, sr: int = MIX_SR) -> None:
    sf.write(str(path), np.clip(audio, -1.0, 1.0), sr, subtype="PCM_16")


def duration_s(path: str | Path) -> float:
    info = sf.info(str(path))
    return info.frames / info.samplerate


def atempo(src: str | Path, out: str | Path, speed: float) -> None:
    run([ffmpeg_bin(), "-y", "-v", "error", "-i", str(src), "-filter:a", f"atempo={speed:.4f}", str(out)],
        what="atempo")


def mux(video: str | Path, audio: str | Path, out: str | Path) -> None:
    run([ffmpeg_bin(), "-y", "-v", "error", "-i", str(video), "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)], what="render mp4")


def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def cache_key(*parts: object) -> str:
    raw = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
