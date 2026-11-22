"""QA server (:9045): judges a dubbed line. Three jobs, each optional:

  POST /score    multipart: audio, text, lang, [ref]  -> {heard, backcheck, similarity}
      heard       what a multilingual speech-to-text hears in the dubbed line
      backcheck   share of the line's words that were heard back (0-1)
      similarity  cosine similarity of speaker embeddings, dubbed line against the speaker's sample (`ref`)
  POST /diarize  multipart: audio  -> {segments: [{start, end, speaker}]}
  GET  /health

Models and licences (checked 23 Nov 2026):
  hear-back   Whisper large-v3-turbo through faster-whisper (MIT; 809 M parameters). The live Whisper on 9030 is a
              Hindi/Hinglish model and cannot hear Tamil or Bengali back; this one can, with lower accuracy on the
              smaller languages (its card says so). `QA_STT_MODEL` picks another one.
  similarity  SpeechBrain ECAPA-TDNN `speechbrain/spkrec-ecapa-voxceleb` (Apache-2.0). NOT ECAPA2, which earlier
              measurements used: its licence is CC-BY-NC-4.0, non-commercial.
  diarization pyannote `speaker-diarization-community-1` (CC-BY-4.0, gated: accept its terms and set HF_TOKEN).
              Off unless QA_DIARIZE=1.

`QA_DEVICE=cpu` (the default) keeps it off the GPU: a Studio line of a few seconds is scored in a few seconds on
CPU, and the card has no room beside v0's servers. `QA_DEVICE=cuda` needs about 2-5 GB (not measured here).

STATUS: NOT run with real models on the build machine. `V1_STUB=1` starts it without them: it "hears" the text it
was given and reports a fixed similarity, so the backend's scoring path can be tested end to end.
"""
import asyncio
import tempfile
import time
import unicodedata
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from common import STUB, env, read_mono

DEVICE = env("QA_DEVICE", "cpu")
STT_MODEL = env("QA_STT_MODEL", "large-v3-turbo")
SPK_MODEL = env("QA_SPK_MODEL", "speechbrain/spkrec-ecapa-voxceleb")
DIARIZE = env("QA_DIARIZE", "0") == "1"
DIAR_MODEL = env("QA_DIAR_MODEL", "pyannote/speaker-diarization-community-1")

app = FastAPI(title="BharatDb v1 QA")
whisper: Any = None
speaker: Any = None
diarizer: Any = None
lock = asyncio.Lock()
state = {"scores": 0, "ms": 0.0}


def words(text: str) -> list[str]:
    kept = "".join(c if unicodedata.category(c)[0] in "LMN" else " " for c in text.lower())
    return kept.split()


def words_heard(said: str, heard: str) -> float:
    """Share of the words in `said` that turn up in `heard` (same word, or the same first four letters)."""
    want, got = words(said), set(words(heard))
    if not want:
        return 0.0
    return sum(1 for w in want if w in got or any(w[:4] == g[:4] for g in got)) / len(want)


def _load() -> None:
    global whisper, speaker, diarizer
    from faster_whisper import WhisperModel
    whisper = WhisperModel(STT_MODEL, device=DEVICE, compute_type="float16" if DEVICE == "cuda" else "int8")
    from speechbrain.inference.speaker import EncoderClassifier
    speaker = EncoderClassifier.from_hparams(source=SPK_MODEL, run_opts={"device": DEVICE})
    if DIARIZE:
        import os

        from pyannote.audio import Pipeline
        diarizer = Pipeline.from_pretrained(DIAR_MODEL, token=os.environ.get("HF_TOKEN"))


@app.on_event("startup")
async def startup() -> None:
    if not STUB:
        await asyncio.get_running_loop().run_in_executor(None, _load)


def _hear(path: str, lang: str) -> str:
    code = lang.split("-")[0] if lang and lang != "indic-auto" else None
    segments, _info = whisper.transcribe(path, language=code, beam_size=5, vad_filter=False)
    return " ".join(s.text.strip() for s in segments).strip()


def _embed(x: np.ndarray) -> np.ndarray:
    import torch
    with torch.no_grad():
        e = speaker.encode_batch(torch.from_numpy(np.ascontiguousarray(x))[None, :]).reshape(-1)
    v = e.float().cpu().numpy()
    return v / (np.linalg.norm(v) + 1e-9)


@app.post("/score")
async def score(audio: UploadFile = File(...), text: str = Form(...), lang: str = Form("hi-IN"),
                ref: UploadFile | None = File(None)) -> dict[str, Any]:
    raw = await audio.read()
    if len(raw) < 800:
        raise HTTPException(422, "empty audio")
    ref_raw = await ref.read() if ref is not None else b""
    t0 = time.perf_counter()
    if STUB:
        heard, sim = text, (0.5 if ref_raw else None)
    else:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(raw)
            path = f.name
        try:
            async with lock:
                loop = asyncio.get_running_loop()
                heard = await loop.run_in_executor(None, _hear, path, lang)
                sim = None
                if ref_raw:
                    a, b = read_mono(raw, 16000), read_mono(ref_raw, 16000)
                    if len(a) > 8000 and len(b) > 8000:
                        ea, eb = await loop.run_in_executor(None, _embed, a), await loop.run_in_executor(None, _embed, b)
                        sim = round(float(np.dot(ea, eb)), 3)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(500, f"scoring failed: {str(e)[:200]}") from e
        finally:
            Path(path).unlink(missing_ok=True)
    ms = (time.perf_counter() - t0) * 1000
    state["scores"] += 1
    state["ms"] += ms
    return {"heard": heard, "backcheck": round(words_heard(text, heard), 3), "similarity": sim, "ms": round(ms)}


@app.post("/diarize")
async def diarize(audio: UploadFile = File(...)) -> dict[str, Any]:
    raw = await audio.read()
    if STUB or diarizer is None:
        if not STUB and not DIARIZE:
            raise HTTPException(503, "diarization is switched off on this server (QA_DIARIZE=1 turns it on)")
        seconds = len(read_mono(raw, 16000)) / 16000 if len(raw) > 800 else 0.0
        return {"segments": [{"start": 0.0, "end": round(seconds, 2), "speaker": "S1"}] if seconds else []}
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(raw)
        path = f.name
    try:
        async with lock:
            out = await asyncio.get_running_loop().run_in_executor(None, diarizer, path)
        ann = getattr(out, "speaker_diarization", out)
        segs = [{"start": round(turn.start, 2), "end": round(turn.end, 2), "speaker": str(label)}
                for turn, _, label in ann.itertracks(yield_label=True)]
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"diarization failed: {str(e)[:200]}") from e
    finally:
        Path(path).unlink(missing_ok=True)
    return {"segments": segs}


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": STUB or whisper is not None, "stub": STUB, "device": DEVICE, "model": STT_MODEL,
            "speaker_model": SPK_MODEL, "diarization": bool(diarizer) or (STUB and DIARIZE),
            "scores": state["scores"], "score_ms_avg": round(state["ms"] / state["scores"]) if state["scores"] else None}
