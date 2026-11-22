"""Build a Studio test video from the hard set's lines: several spoken lines with pauses, on a plain picture.

  python -m eval.v1.make_video --set <folder with 00.wav ..> --out <video.mp4> [--lines 12] [--gap 0.9]

The Live test reel is one unbroken 25 s line, which makes a Studio job of exactly one line. This gives a job of
many lines whose words are known (`hard_set.json`), so the transcript and each dubbed line can be checked.
The speech is from hosted stock voices: a machine's voice, not a person's.
"""
import argparse
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lines", type=int, default=12)
    ap.add_argument("--gap", type=float, default=0.9)
    ap.add_argument("--first", type=int, default=0)
    a = ap.parse_args()
    from app.shared import audio_utils as au
    sr = 44100
    parts: list[np.ndarray] = [np.zeros(int(sr * 0.4), dtype=np.float32)]
    for i in range(a.first, a.first + a.lines):
        x, rate = sf.read(str(Path(a.set) / f"{i:02}.wav"), dtype="float32", always_2d=True)
        x = x.mean(axis=1)
        if rate != sr:
            x = np.interp(np.linspace(0, len(x) - 1, int(len(x) * sr / rate)), np.arange(len(x)), x).astype(np.float32)
        parts += [x, np.zeros(int(sr * a.gap), dtype=np.float32)]
    audio = np.concatenate(parts)
    seconds = len(audio) / sr
    wav = Path(tempfile.gettempdir()) / "bd_v1_eval_video.wav"
    sf.write(str(wav), audio, sr)
    au.run([au.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=0x202830:s=320x240:r=10:d={seconds:.2f}",
            "-i", str(wav), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-shortest", a.out],
           what="make eval video")
    wav.unlink(missing_ok=True)
    print(f"{a.out}: {a.lines} lines, {seconds:.1f} s")


if __name__ == "__main__":
    main()
