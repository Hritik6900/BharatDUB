"""A second voice engine for the GPU engine: Indic-Mio (SPRINGLab/Indic-Mio, Apache-2.0), a 0.6 B language model
that writes speech tokens, and MioCodec, which turns the tokens into sound in the speaker's voice. 127.0.0.1 only.

  vllm serve SPRINGLab/Indic-Mio --port 9021 --served-model-name mio ...        (the model, start_mio.sh)
  .venv_mio/bin/python -m uvicorn mio_engine:app --host 127.0.0.1 --port 9040   (this file)

Why beside IndicF5: IndicF5 makes a whole line in one go and needs about 7 s of the speaker plus the exact words
spoken in it. This model speaks token by token (25 tokens for a second of sound), takes the speaker from the sound
alone (no transcript), reads Latin letters, and also speaks English.

Same calls as voice_engine_live.py, so the backend talks to either:
  POST /ref   multipart: session_id, audio (ref_text is accepted and ignored)   -> remembers the speaker
  POST /tts   json {session_id, text, lang, fmt, speed}                         -> audio; X-Sample-Rate, X-Format,
              X-Synth-Ms (whole line), X-Tokens-Ms (the language model's part)
  GET  /health
"""
import asyncio
import io
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import soundfile as sf
import torch
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from miocodec import MioCodecModel
from miocodec.util import load_audio
from pydantic import BaseModel

LLM_URL = os.environ.get("MIO_LLM_URL", "http://127.0.0.1:9021/v1")
LLM_MODEL = os.environ.get("MIO_LLM_MODEL", "mio")
CODEC = os.environ.get("MIO_CODEC", "Aratako/MioCodec-25Hz-44.1kHz-v2")
TEMPERATURE = float(os.environ.get("MIO_TEMPERATURE", "0.8"))
MAX_REF_S = 20.0
TOKEN = re.compile(r"<\|s_(\d+)\|>")
TOKENS_A_SECOND = 25

app = FastAPI()
codec: MioCodecModel | None = None
refs: dict[str, torch.Tensor] = {}     # session -> the speaker's embedding
llm = httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=3.0))
decode_lock = asyncio.Lock()


@app.on_event("startup")
def _load() -> None:
    global codec
    t0 = time.perf_counter()
    codec = MioCodecModel.from_pretrained(CODEC).eval().to("cuda")
    print(f"[mio-engine] {CODEC} ready in {time.perf_counter() - t0:.1f} s, {codec.config.sample_rate} Hz")


def _embed(path: str) -> torch.Tensor:
    assert codec is not None
    wave = load_audio(path, sample_rate=codec.config.sample_rate)
    wave = wave[..., : int(MAX_REF_S * codec.config.sample_rate)].to("cuda", dtype=torch.float32)
    with torch.inference_mode():
        return codec.encode(wave, return_content=False, return_global=True).global_embedding


def _decode(tokens: list[int], emb: torch.Tensor, samples: int | None) -> np.ndarray:
    assert codec is not None
    with torch.inference_mode():
        wave = codec.decode(global_embedding=emb, content_token_indices=torch.tensor(tokens, dtype=torch.long, device="cuda"),
                            target_audio_length=samples)
    return wave.flatten().float().cpu().numpy()


def _encode(wave: np.ndarray, sr: int, fmt: str) -> bytes:
    peak = float(np.max(np.abs(wave))) if wave.size else 0.0
    if peak > 0.98:
        wave = wave * (0.98 / peak)
    pcm = (wave * 32767.0).astype("<i2")
    if fmt == "pcm":
        return pcm.tobytes()
    buf = io.BytesIO()
    sf.write(buf, pcm, sr, format="MP3", subtype="MPEG_LAYER_III", compression_level=0.7, bitrate_mode="VARIABLE")
    return buf.getvalue()


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": codec is not None, "model": "indic-mio", "codec": CODEC, "voices": len(refs),
            "sample_rate": codec.config.sample_rate if codec else None,
            "gpu_gb": round(torch.cuda.memory_allocated() / 1e9, 2)}


@app.post("/ref")
async def ref(session_id: str = Form(...), audio: UploadFile = File(...), ref_text: str = Form("")) -> dict[str, Any]:
    raw = await audio.read()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(raw)
        path = f.name
    try:
        t0 = time.perf_counter()
        refs[session_id] = await asyncio.get_running_loop().run_in_executor(None, _embed, path)
    finally:
        Path(path).unlink(missing_ok=True)
    while len(refs) > 300:
        refs.pop(next(iter(refs)))
    return {"ok": True, "ms": round((time.perf_counter() - t0) * 1000)}


class TTS(BaseModel):
    session_id: str
    text: str
    lang: str = ""
    fmt: str = "mp3"
    speed: float = 1.0     # > 1 = faster: the codec fits the same tokens into less time
    nfe: int = 0           # accepted for the other engine's sake, not used here


@app.post("/tts")
async def tts(req: TTS) -> Response:
    emb = refs.get(req.session_id)
    if emb is None:
        raise HTTPException(404, "no voice for this session: send /ref first")
    text = " ".join(req.text.split())
    if not text:
        raise HTTPException(400, "empty text")
    t0 = time.perf_counter()
    body = {"model": LLM_MODEL, "messages": [{"role": "user", "content": text}], "temperature": TEMPERATURE,
            "top_p": 1.0, "max_tokens": 900, "skip_special_tokens": False}
    try:
        r = await llm.post(LLM_URL + "/chat/completions", json=body)
        r.raise_for_status()
        out = r.json()["choices"][0]["message"]["content"] or ""
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
        raise HTTPException(502, f"speech tokens: {str(e)[:160]}") from e
    tokens = [int(x) for x in TOKEN.findall(out)]
    if len(tokens) < 3:
        raise HTTPException(502, "the model wrote no speech tokens")
    t1 = time.perf_counter()
    assert codec is not None
    sr = int(codec.config.sample_rate)
    speed = max(0.6, min(2.0, req.speed or 1.0))
    samples = int(len(tokens) / TOKENS_A_SECOND * sr / speed) if abs(speed - 1.0) > 0.02 else None
    async with decode_lock:
        wave = await asyncio.get_running_loop().run_in_executor(None, _decode, tokens, emb, samples)
    data = _encode(wave, sr, req.fmt)
    done = time.perf_counter()
    return Response(content=data, media_type="application/octet-stream", headers={
        "X-Sample-Rate": str(sr), "X-Format": req.fmt, "X-Synth-Ms": str(round((done - t0) * 1000)),
        "X-Tokens-Ms": str(round((t1 - t0) * 1000)), "X-Tokens": str(len(tokens))})
