"""Maya 2 Native (:9042) behind the same calls as the IndicF5 engines, so the backend treats it as one more voice.

  POST /ref   multipart: session_id, ref_text, audio  -> registers the voice (3-10 s of speech + its exact words)
  POST /tts   json {session_id, text, lang, speed, fmt}  -> audio (24 kHz)
  GET  /health

Model: `maya-research/maya2-native` (Apache-2.0, not gated; 2.5 B parameters, about 5 GB on disk; the card gives
7.7 GB of GPU memory for one seat, 9.2 GB while loading). It runs in its own engine (package `maya3`), not vLLM.
Languages: as, bn, en, gu, hi, kn, ml, mr, or, pa, ta, te. The card documents no speed or duration control, so
`speed` is accepted and ignored: fitting a line to its slot is done by the caller.

STATUS: written from the model card's example (`Maya3TTS.from_pretrained`, `register_voice`, `generate`) and NOT
run: the model does not fit beside v0's servers (docs/v1/NEEDS_APPROVAL.md). `V1_STUB=1` starts it without the model.
"""
import asyncio
import time
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from common import SR, STUB, encode, env, stub_wave

REPO = env("MAYA_REPO", "maya-research/maya2-native")
REVISION = env("MAYA_REVISION", "main")         # pin to the full commit hash when first deployed (card: 87a83efd...)
SEATS = int(env("MAYA_SEATS", "1"))
REF_DIR = Path(env("REF_DIR", "/tmp/voice_refs_maya"))
LANGS = {"hi-IN": "hi", "ta-IN": "ta", "te-IN": "te", "bn-IN": "bn", "kn-IN": "kn", "ml-IN": "ml", "mr-IN": "mr",
         "gu-IN": "gu", "pa-IN": "pa", "en-IN": "en"}

app = FastAPI(title="BharatDb v1 Maya voice")
tts_model: Any = None
voices: dict[str, int] = {}                      # session -> version
lock = asyncio.Semaphore(max(1, SEATS))


def _load() -> None:
    global tts_model
    from maya3 import Maya3TTS
    tts_model = Maya3TTS.from_pretrained(REPO, max_seats=SEATS)


@app.on_event("startup")
async def startup() -> None:
    REF_DIR.mkdir(parents=True, exist_ok=True)
    if not STUB:
        await asyncio.get_running_loop().run_in_executor(None, _load)


@app.post("/ref")
async def set_ref(session_id: str = Form(...), ref_text: str = Form(...), audio: UploadFile = File(...),
                  lang: str = Form("hi-IN")) -> dict[str, Any]:
    raw = await audio.read()
    if len(raw) < 2000 or not ref_text.strip():
        raise HTTPException(422, "need a voice sample and the words spoken in it")
    version = voices.get(session_id, 0) + 1
    path = REF_DIR / f"{abs(hash(session_id))}-{version}.wav"
    path.write_bytes(raw)
    if not STUB:
        try:
            await asyncio.get_running_loop().run_in_executor(None, lambda: tts_model.register_voice(
                session_id, ref_audio=str(path), ref_text=ref_text.strip(), lang=LANGS.get(lang, "hi")))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(422, f"could not register the voice: {str(e)[:160]}") from e
    voices[session_id] = version
    return {"ok": True, "session_id": session_id, "version": version}


class Line(BaseModel):
    session_id: str
    text: str
    lang: str = "hi-IN"
    speed: float = 1.0      # accepted for the other engines' sake; this model has no speed control
    fmt: str = "pcm"
    nfe: int = 0


@app.post("/tts")
async def tts(req: Line) -> Response:
    if req.session_id not in voices:
        raise HTTPException(409, "no voice sample for this session: POST /ref first")
    if req.lang not in LANGS:
        raise HTTPException(422, f"language not spoken: {req.lang}")
    if not req.text.strip():
        raise HTTPException(422, "empty text")
    async with lock:
        t0 = time.perf_counter()
        try:
            if STUB:
                wave = stub_wave(req.text)
            else:
                out = await asyncio.get_running_loop().run_in_executor(None, lambda: tts_model.generate(
                    req.text.strip(), lang=LANGS[req.lang], voice=req.session_id))
                wave = np.asarray(out, dtype=np.float32).reshape(-1)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(500, f"synthesis failed: {str(e)[:200]}") from e
        ms = (time.perf_counter() - t0) * 1000
    fmt = req.fmt if req.fmt in ("opus", "mp3") else "pcm"
    return Response(content=encode(wave, fmt), media_type="application/octet-stream", headers={
        "X-Synth-Ms": f"{ms:.0f}", "X-Sample-Rate": str(SR), "X-Format": fmt, "X-Speed": "1.0",
        "X-Audio-Ms": f"{wave.size / SR * 1000:.0f}"})


@app.get("/health")
async def health() -> dict[str, Any]:
    gpu = 0.0
    if not STUB and tts_model is not None:
        import torch
        gpu = round(torch.cuda.memory_allocated() / 1e9, 2)
    return {"ok": STUB or tts_model is not None, "model": REPO, "revision": REVISION, "stub": STUB,
            "voices": len(voices), "seats": SEATS, "gpu_gb": gpu}
