"""Stage 10: mux dubbed audio into the original video (copy video, AAC audio) + SRT."""
from pathlib import Path

from app.shared import audio_utils as au
from app.shared.srt import write_srt


def render(video: Path, mix_wav: Path, out_mp4: Path, out_srt: Path,
           cues: list[tuple[float, float, str]]) -> None:
    au.mux(video, mix_wav, out_mp4)
    write_srt(out_srt, cues)
