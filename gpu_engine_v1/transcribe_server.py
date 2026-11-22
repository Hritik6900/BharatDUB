"""Indic Transcribe (:9043): speech-to-text for Studio HQ, clips of up to 30 s, not streaming.

  POST /stt     multipart: audio, lang (hi-IN, ta-IN, ...)  -> {text, lang, ms}
  GET  /health

Model: `bodhan-ai/indic-transcribe-core` (1.2 B parameters, 4.6 GB checkpoint; the card gives 9.2 GiB of GPU memory
at batch 8 on its long-audio path; 25 languages, all of ours and Indian English). Gated on Hugging Face (accept its
terms, then `hf auth login`). LICENCE: "Indic Open Model License v1.0": self-hosting and commercial use are free,
but offering it as a hosted service that others call needs the authors' written sign-off, and attribution is
required. Whether a dubbing site counts is a decision for the user (docs/v1/NEEDS_APPROVAL.md).

STATUS: written from the model card's example (`IndicTranscribe.from_pretrained`, `asr(path, lang=...)`) and NOT
run. `V1_STUB=1` starts it without the model and answers with a fixed line.
"""
import asyncio
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from common import STUB, env

REPO = env("TRANSCRIBE_REPO", "bodhan-ai/indic-transcribe-core")
REVISION = env("TRANSCRIBE_REVISION", "main")   # pin to the full commit hash when first deployed (card: e083ab7d...)
MAX_SECONDS = float(env("TRANSCRIBE_MAX_S", "30"))

app = FastAPI(title="BharatDb v1 Indic Transcribe")
asr: Any = None
lock = asyncio.Lock()
state = {"calls": 0, "ms": 0.0}


def _load() -> None:
    global asr
    from huggingface_hub import snapshot_download
    model_dir = snapshot_download(REPO, revision=REVISION)
    sys.path.insert(0, model_dir)
    from indic_transcribe import IndicTranscribe
    asr = IndicTranscribe.from_pretrained(model_dir)


@app.on_event("startup")
async def startup() -> None:
    if not STUB:
        await asyncio.get_running_loop().run_in_executor(None, _load)


@app.post("/stt")
async def stt(audio: UploadFile = File(...), lang: str = Form("hi-IN")) -> dict[str, Any]:
    raw = await audio.read()
    if len(raw) < 800:
        raise HTTPException(422, "empty audio")
    code = lang.split("-")[0] if lang != "indic-auto" else "hi"
    t0 = time.perf_counter()
    if STUB:
        text = "yah ek stub hai, asli model load nahin hua"
    else:
        with tempfile.NamedTemporaryFile(suffix=Path(audio.filename or "a.wav").suffix or ".wav", delete=False) as f:
            f.write(raw)
            path = f.name
        try:
            import soundfile as sf
            info = sf.info(path)
            if info.duration > MAX_SECONDS + 15:   # the model refuses a single pass over 45 s
                raise HTTPException(422, f"clip is {info.duration:.0f} s; send clips of up to {MAX_SECONDS:.0f} s")
            async with lock:
                out = await asyncio.get_running_loop().run_in_executor(None, lambda: asr(path, lang=code))
            text = out if isinstance(out, str) else str(getattr(out, "text", None) or (out.get("text") if isinstance(out, dict) else out))
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            raise HTTPException(500, f"transcription failed: {str(e)[:200]}") from e
        finally:
            Path(path).unlink(missing_ok=True)
    ms = (time.perf_counter() - t0) * 1000
    state["calls"] += 1
    state["ms"] += ms
    return {"text": text.strip(), "lang": lang, "ms": round(ms)}


@app.get("/health")
async def health() -> dict[str, Any]:
    gpu = 0.0
    if not STUB and asr is not None:
        import torch
        gpu = round(torch.cuda.memory_allocated() / 1e9, 2)
    return {"ok": STUB or asr is not None, "model": REPO, "revision": REVISION, "stub": STUB, "calls": state["calls"],
            "decode_ms_avg": round(state["ms"] / state["calls"]) if state["calls"] else None, "gpu_gb": gpu}
