"""Runs ON the GPU machine: Demucs (htdemucs) vocals / background split for Studio, on the GPU.

  PYTHONPATH=~/voice_engine/demucs_pkgs python -m uvicorn sep_engine:app --host 127.0.0.1 --port 9010

  POST /separate  multipart: audio (FLAC or WAV, 44.1 kHz)  ->  8 bytes (length of the first file, big endian),
                  then vocals.flac, then background.flac (both mono, 44.1 kHz). Header X-Separate-Ms = GPU time.
  GET  /health

Same maths as backend/app/studio/demucs_worker.py, so the result matches the CPU path.
"""
import asyncio
import io
import time

import numpy as np
import soundfile as sf
import torch
from demucs.apply import apply_model
from demucs.pretrained import get_model
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response

app = FastAPI(title="Bharat Dub separation engine")
model = None
lock = asyncio.Lock()


def _separate(raw: bytes) -> tuple[bytes, bytes]:
    wav, sr = sf.read(io.BytesIO(raw), dtype="float32", always_2d=True)
    if sr != model.samplerate:
        raise ValueError(f"expected {model.samplerate} Hz input, got {sr}")
    x = torch.from_numpy(wav.T.copy())
    if x.shape[0] == 1:
        x = x.repeat(model.audio_channels, 1)
    ref = x.mean(0)
    mean, std = ref.mean(), ref.std() + 1e-8
    with torch.no_grad():
        sources = apply_model(model, ((x - mean) / std)[None], device="cuda", split=True, overlap=0.25,
                              progress=False)[0].cpu()
    sources = sources * std + mean
    vocals = sources[model.sources.index("vocals")]
    background = sources.sum(0) - vocals
    out = []
    for stem in (vocals, background):
        buf = io.BytesIO()
        sf.write(buf, stem.mean(0).numpy().astype(np.float32), sr, format="FLAC", subtype="PCM_16")
        out.append(buf.getvalue())
    return out[0], out[1]


@app.on_event("startup")
async def startup() -> None:
    global model
    model = get_model("htdemucs")
    model.eval().to("cuda")
    await asyncio.get_running_loop().run_in_executor(None, _separate, _silence())
    print("[sep-engine] htdemucs ready on the GPU")


def _silence() -> bytes:
    buf = io.BytesIO()
    sf.write(buf, np.zeros(44100 * 2, dtype=np.float32), 44100, format="FLAC", subtype="PCM_16")
    return buf.getvalue()


@app.post("/separate")
async def separate(audio: UploadFile = File(...)) -> Response:
    raw = await audio.read()
    t0 = time.perf_counter()
    async with lock:  # one job at a time on the GPU
        try:
            vocals, background = await asyncio.get_running_loop().run_in_executor(None, _separate, raw)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
    ms = (time.perf_counter() - t0) * 1000
    return Response(content=len(vocals).to_bytes(8, "big") + vocals + background,
                    media_type="application/octet-stream", headers={"X-Separate-Ms": f"{ms:.0f}"})


@app.get("/health")
async def health() -> dict:
    return {"ok": model is not None, "gpu_gb": round(torch.cuda.memory_allocated() / 1e9, 2)}
