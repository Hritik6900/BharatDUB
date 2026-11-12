"""Demucs in-process separation without torchaudio file I/O (soundfile instead).

Usage: python -m app.studio.demucs_worker full.wav vocals_out.wav background_out.wav
"""
import sys

import numpy as np
import soundfile as sf
import torch
from demucs.apply import apply_model
from demucs.pretrained import get_model


def main(inp: str, vocals_out: str, bg_out: str) -> None:
    torch.set_num_threads(max(1, torch.get_num_threads()))
    model = get_model("htdemucs")
    model.eval()
    wav, sr = sf.read(inp, dtype="float32", always_2d=True)
    if sr != model.samplerate:
        raise SystemExit(f"expected {model.samplerate} Hz input, got {sr}")
    x = torch.from_numpy(wav.T.copy())
    if x.shape[0] == 1:
        x = x.repeat(model.audio_channels, 1)
    ref = x.mean(0)
    mean, std = ref.mean(), ref.std() + 1e-8
    with torch.no_grad():
        sources = apply_model(model, ((x - mean) / std)[None], device="cpu", split=True, overlap=0.25,
                              progress=False)[0]
    sources = sources * std + mean
    vi = model.sources.index("vocals")
    vocals = sources[vi]
    background = sources.sum(0) - vocals
    sf.write(vocals_out, vocals.mean(0).numpy().astype(np.float32), sr, subtype="PCM_16")
    sf.write(bg_out, background.mean(0).numpy().astype(np.float32), sr, subtype="PCM_16")


if __name__ == "__main__":
    main(*sys.argv[1:4])
