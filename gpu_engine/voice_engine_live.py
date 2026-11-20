"""Runs ON the GPU machine: IndicF5 as a small voice-copy server for Live and Streamer Mode.

  NFE=12 python -m uvicorn voice_engine_live:app --host 127.0.0.1 --port 9001     (start_live.sh runs three of these)

  POST /ref     multipart: session_id, ref_text, audio (3-10 s of speech, any sample rate)  -> the voice to copy
  POST /tts     json: {session_id, text, lang, speed, fmt}  -> audio (24 kHz mono; raw PCM16, or OGG/Opus with fmt="opus")
                headers: X-Synth-Ms, X-Sample-Rate, X-Format, X-Ref-Version, X-Speed
  GET  /health

One process speaks one line at a time; run several processes for several lines at once (measured: replicas inside one
process do not run in parallel, separate processes do). The model is gated on Hugging Face: `hf auth login` once.
Written again on 20 Nov 2026 for a new machine; the first engine was lost with the old one.
"""
import asyncio
import glob
import io
import os
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from f5_tts.infer.utils_infer import infer_process, load_model, load_vocoder, preprocess_ref_audio_text
from f5_tts.model import DiT
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from huggingface_hub import snapshot_download
from pydantic import BaseModel
from safetensors.torch import load_file

REPO = "ai4bharat/IndicF5"
NFE = int(os.environ.get("NFE", "12"))          # denoising steps: 32 is the model's default, 12 is about 2.5x faster
# bf16 is about 10% faster than fp32 with clean output; fp16 gave NaN (measured 20 Nov 2026).
BF16 = os.environ.get("PRECISION", "bf16") == "bf16"
SR = 24000
REF_DIR = Path(os.environ.get("REF_DIR", "/tmp/voice_refs"))

app = FastAPI(title="Bharat Dub voice engine")
model = None
vocoder = None
refs: dict[str, dict] = {}          # session_id -> {"audio": processed path, "text": str, "version": int}
lock = asyncio.Lock()               # one line at a time on this process


def quiet(*_a, **_k) -> None:
    pass


def _load() -> None:
    """Build the network and the vocoder, then fill both from the one weight file of the Hugging Face repo."""
    global model, vocoder
    snap = Path(snapshot_download(REPO, allow_patterns=["model.safetensors", "checkpoints/vocab.txt", "prompts/*"]))
    vocoder = load_vocoder(vocoder_name="vocos", is_local=False, device="cuda")
    model = load_model(DiT, dict(dim=1024, depth=22, heads=16, ff_mult=2, text_dim=512, conv_layers=4),
                       mel_spec_type="vocos", vocab_file=str(snap / "checkpoints" / "vocab.txt"), device="cuda")
    state = load_file(str(snap / "model.safetensors"), device="cuda")
    # The repo stores the weights as saved from torch.compile wrappers: "ema_model._orig_mod.<name>".
    for target, prefix in ((model, "ema_model._orig_mod."), (vocoder, "vocoder._orig_mod.")):
        part = {k[len(prefix):]: v for k, v in state.items() if k.startswith(prefix)}
        missing, unexpected = target.load_state_dict(part, strict=False)
        print(f"[voice-engine] {prefix} {len(part)} tensors, missing {len(missing)}, unexpected {len(unexpected)}")
    model.eval()
    # Warm up on one of the repo's own prompts, so the first real line is not the slow one.
    wav = sorted(glob.glob(str(snap / "prompts" / "*.wav")))
    if wav:
        audio, text = preprocess_ref_audio_text(wav[0], "नमस्ते, यह एक परीक्षण है।", show_info=quiet)
        _synth(audio, text, "नमस्ते।", 1.0)


def _synth(ref_audio: str, ref_text: str, text: str, speed: float) -> np.ndarray:
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16, enabled=BF16):
        wave, _sr, _spec = infer_process(ref_audio, ref_text, text, model, vocoder, mel_spec_type="vocos",
                                         nfe_step=NFE, show_info=quiet, speed=speed, device="cuda")
    return np.asarray(wave, dtype=np.float32)


def _encode(wave: np.ndarray, fmt: str) -> bytes:
    peak = float(np.max(np.abs(wave))) if wave.size else 0.0
    if peak > 0.98:
        wave = wave * (0.98 / peak)
    pcm = (wave * 32767.0).astype("<i2")
    if fmt != "opus":
        return pcm.tobytes()
    buf = io.BytesIO()
    sf.write(buf, pcm, SR, format="OGG", subtype="OPUS")
    return buf.getvalue()


@app.on_event("startup")
async def startup() -> None:
    REF_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    await asyncio.get_running_loop().run_in_executor(None, _load)
    print(f"[voice-engine] ready in {time.perf_counter() - t0:.1f} s, NFE {NFE}")


@app.post("/ref")
async def set_ref(session_id: str = Form(...), ref_text: str = Form(...), audio: UploadFile = File(...)) -> dict:
    raw = await audio.read()
    if len(raw) < 2000 or not ref_text.strip():
        raise HTTPException(422, "need a voice sample and the words spoken in it")
    version = refs.get(session_id, {}).get("version", 0) + 1
    path = REF_DIR / f"{os.getpid()}-{abs(hash(session_id))}-{version}.wav"
    path.write_bytes(raw)
    try:
        processed, text = await asyncio.get_running_loop().run_in_executor(
            None, lambda: preprocess_ref_audio_text(str(path), ref_text.strip(), show_info=quiet))
    except Exception as e:  # noqa: BLE001 - an unreadable sample must not take the engine down
        raise HTTPException(422, f"could not read the sample: {str(e)[:160]}") from e
    refs[session_id] = {"audio": processed, "text": text, "version": version}
    return {"ok": True, "session_id": session_id, "version": version}


class Line(BaseModel):
    session_id: str
    text: str
    lang: str = ""
    speed: float = 1.0   # > 1 = faster speech
    fmt: str = "pcm"     # "opus" = OGG/Opus, about a tenth of the bytes


@app.post("/tts")
async def tts(req: Line) -> Response:
    ref = refs.get(req.session_id)
    if not ref:
        raise HTTPException(409, "no voice sample for this session: POST /ref first")
    if not req.text.strip():
        raise HTTPException(422, "empty text")
    speed = max(0.4, min(1.5, req.speed))
    async with lock:
        t0 = time.perf_counter()
        try:
            wave = await asyncio.get_running_loop().run_in_executor(None, _synth, ref["audio"], ref["text"], req.text, speed)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(500, f"synthesis failed: {str(e)[:200]}") from e
        ms = (time.perf_counter() - t0) * 1000
    fmt = "opus" if req.fmt == "opus" else "pcm"
    return Response(content=_encode(wave, fmt), media_type="application/octet-stream", headers={
        "X-Synth-Ms": f"{ms:.0f}", "X-Sample-Rate": str(SR), "X-Format": fmt, "X-Ref-Version": str(ref["version"]),
        "X-Speed": str(speed), "X-Audio-Ms": f"{wave.size / SR * 1000:.0f}"})


@app.get("/health")
async def health() -> dict:
    return {"ok": model is not None, "nfe": NFE, "bf16": BF16, "voices": len(refs),
            "gpu_gb": round(torch.cuda.memory_allocated() / 1e9, 2) if model is not None else 0}
