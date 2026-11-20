"""Runs ON the GPU machine: does running both halves of classifier-free guidance in one batch give the same audio, faster?

  .venv2/bin/python bench_cfg.py ref.wav "words spoken in ref.wav"

For each setting: time per line, where the time goes, GPU utilisation while lines run back to back, and how far the
audio is from the library's own two-pass result made from the same noise.
"""
import subprocess
import sys
import threading
import time

import numpy as np
import torch

import voice_engine_live as e

LINES = ["இன்று நாம் ஒரு புதிய விளையாட்டை விளையாடப் போகிறோம் நண்பர்களே",
         "আজ আমরা একটি নতুন খেলা খেলতে যাচ্ছি বন্ধুরা, তৈরি থাকো",
         "ਅੱਜ ਅਸੀਂ ਇੱਕ ਨਵੀਂ ਖੇਡ ਖੇਡਣ ਜਾ ਰਹੇ ਹਾਂ ਦੋਸਤੋ, ਤਿਆਰ ਰਹੋ",
         "అందరికీ నమస్కారం, ఈ రోజు మనం కొత్త ఆట ఆడబోతున్నాం"]


class Timer:
    """Wraps a callable and adds up the GPU-synchronised time spent inside it."""

    def __init__(self, fn):
        self.fn, self.s, self.n = fn, 0.0, 0

    def __call__(self, *a, **k):
        torch.cuda.synchronize()
        t = time.perf_counter()
        out = self.fn(*a, **k)
        torch.cuda.synchronize()
        self.s += time.perf_counter() - t
        self.n += 1
        return out


class Counter:
    """Counts calls without touching the timing."""

    def __init__(self, fn):
        self.fn, self.n = fn, 0

    def __call__(self, *a, **k):
        self.n += 1
        return self.fn(*a, **k)


def gpu_util(seconds: float, work) -> tuple[float, int]:
    """Average and peak GPU utilisation (%) while `work()` runs in a loop for `seconds`."""
    p = subprocess.Popen(["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits", "-lms", "100"],
                         stdout=subprocess.PIPE, text=True)
    stop = time.perf_counter() + seconds
    n = 0
    while time.perf_counter() < stop:
        work(n)
        n += 1
    p.terminate()
    vals = [int(x) for x in p.stdout.read().split() if x.strip().isdigit()][2:]
    return (sum(vals) / max(1, len(vals)), max(vals or [0]))


def run(label: str, audio: str, text: str) -> list[np.ndarray]:
    sample = Timer(e.model.sample)
    e.model.sample = sample
    first_block = getattr(e.model.transformer, "dit", e.model.transformer).transformer_blocks[0]
    calls = Counter(first_block.forward)
    first_block.forward = calls
    waves, times = [], []
    try:
        for i in range(len(LINES) * 2):
            torch.manual_seed(1000 + i % len(LINES))
            torch.cuda.synchronize()
            t = time.perf_counter()
            w = e._synth(audio, text, LINES[i % len(LINES)], 1.0)
            torch.cuda.synchronize()
            times.append(time.perf_counter() - t)
            waves.append(w)
    finally:
        del e.model.sample              # back to the class's own method
        del first_block.forward
    half = len(LINES)
    line_ms = sorted(times[half:])[half // 2] * 1000
    in_sample = sample.s / sample.n * 1000
    avg, peak = gpu_util(6.0, lambda n: e._synth(audio, text, LINES[n % len(LINES)], 1.0))
    print(f"{label:34} line {line_ms:5.0f} ms | in the sampler {in_sample:5.0f} ms, {calls.n // sample.n:2d} network calls a line | "
          f"GPU busy {avg:3.0f}% avg, {peak}% peak | audio {np.mean([len(w) for w in waves[half:]]) / e.SR:.1f} s")
    return waves[half:]


def compare(a: list[np.ndarray], b: list[np.ndarray]) -> str:
    out = []
    for x, y in zip(a, b):
        n = min(len(x), len(y))
        x, y = x[:n].astype(np.float64), y[:n].astype(np.float64)
        err = np.sqrt(np.mean((x - y) ** 2)) / (np.sqrt(np.mean(x ** 2)) + 1e-12)
        out.append(f"{20 * np.log10(err + 1e-12):.0f} dB")
    return ", ".join(out)


def mel_gap(a: list[np.ndarray], b: list[np.ndarray]) -> str:
    """Average distance between the two sounds on a log-mel scale, in dB (what the ear hears, not the waveform:
    the vocoder invents phase, so two renderings of the same sound differ sample by sample)."""
    import torchaudio
    mel = torchaudio.transforms.MelSpectrogram(e.SR, n_fft=1024, hop_length=256, n_mels=100)
    out = []
    for x, y in zip(a, b):
        n = min(len(x), len(y))
        mx, my = (10 * torch.log10(mel(torch.from_numpy(np.ascontiguousarray(w[:n])).float()) + 1e-5) for w in (x, y))
        loud = mx > mx.max() - 50          # ignore the silent corners of the picture
        out.append(f"{(mx - my).abs()[loud].mean().item():.1f}")
    return ", ".join(out) + " dB"


def main() -> None:
    e._load()
    audio, text = e.preprocess_ref_audio_text(sys.argv[1], sys.argv[2], show_info=e.quiet)
    dit = getattr(e.model.transformer, "dit", e.model.transformer)
    got = {}
    for bf16 in (False, True):
        e.BF16 = bf16
        name = "bf16" if bf16 else "fp32"
        e.model.transformer = dit
        got[name, "two"] = run(f"{name}, two passes (library)", audio, text)
        e.model.transformer = e.BatchedGuidance(dit)
        got[name, "one"] = run(f"{name}, one batched pass", audio, text)
        if bf16:
            for nfe in (12, 16):
                e.NFE = nfe
                got[name, f"one-nfe{nfe}"] = run(f"{name}, one batched pass, {nfe} steps", audio, text)
    ref = got["fp32", "two"]
    print("waveform distance from fp32 two passes:")
    for k in (("fp32", "one"), ("bf16", "two"), ("bf16", "one")):
        print(f"   {k[0]} {k[1]:4}: {compare(ref, got[k])}")
    print("log-mel distance from fp32 two passes (same noise, same steps):")
    for k in (("fp32", "one"), ("bf16", "two"), ("bf16", "one")):
        print(f"   {k[0]} {k[1]:4}: {mel_gap(ref, got[k])}")
    print(f"   between the two bf16 versions: {mel_gap(got['bf16', 'two'], got['bf16', 'one'])}")


if __name__ == "__main__":
    main()
