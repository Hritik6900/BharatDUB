"""Stages 1-2: ingest (probe + reject) and extract 44.1 kHz mono WAV."""
from pathlib import Path

from app.shared import audio_utils as au


class IngestError(ValueError):
    """User-facing reason a video was rejected."""


def ingest(src: Path, max_seconds: int) -> float:
    try:
        info = au.probe(src)
    except au.FFmpegError as e:
        raise IngestError("Could not read this file. Upload an MP4, MOV or WebM video.") from e
    if not info["has_video"]:
        raise IngestError("This file has no video track.")
    if not info["has_audio"]:
        raise IngestError("This video has no audio track to dub.")
    if info["duration"] <= 0:
        raise IngestError("Could not read the video length.")
    if info["duration"] > max_seconds:
        raise IngestError(f"Video is {info['duration']:.0f} s long; the limit is {max_seconds} s.")
    return info["duration"]


def extract(src: Path, out_wav: Path) -> None:
    au.extract_wav(src, out_wav, au.MIX_SR)
