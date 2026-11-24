"""QA server (:9045): judges a dubbed line. Three jobs, each optional:

  POST /score    multipart: audio, text, lang, [ref]  -> {heard, backcheck, similarity}
      heard       what a multilingual speech-to-text hears in the dubbed line
      backcheck   share of the line's words that were heard back (0-1)
      similarity  cosine similarity of speaker embeddings, dubbed line against the speaker's sample (`ref`)
  POST /diarize  multipart: audio  -> {segments: [{start, end, speaker}]}
  POST /similarity  multipart: audio, ref  -> {similarity}   (the speaker model alone; no words are heard)
  GET  /health
  GET  /gpu      what `nvidia-smi` says on this machine (memory, use, temperature, power, memory per process);
                 read-only, loads nothing. The status page shows it as the GPU: from the laptop the card cannot be seen.

Models and licences (checked 23 Nov 2026; the speaker model again on 25 Nov 2026, docs/v1/MODELS.md):
  hear-back   Whisper large-v3-turbo through faster-whisper (MIT; 809 M parameters). The live Whisper on 9030 is a
              Hindi/Hinglish model and cannot hear Tamil or Bengali back; this one can, with lower accuracy on the
              smaller languages (its card says so). `QA_STT_MODEL` picks another one.
  similarity  SpeechBrain ECAPA-TDNN `speechbrain/spkrec-ecapa-voxceleb` (Apache-2.0). NOT ECAPA2, which earlier
              measurements used: its licence is CC-BY-NC-4.0, non-commercial. `QA_SPK_MODEL` picks another one,
              but only a model listed in SPK_LICENCES as open to commercial use is loaded; any other (ECAPA2
              included) is refused unless QA_SPK_ALLOW_NONCOMMERCIAL=1 is set for a measurement that ships nothing.
  diarization pyannote `speaker-diarization-community-1` (CC-BY-4.0, gated: accept its terms and set HF_TOKEN).
              Off unless QA_DIARIZE=1.

`QA_DEVICE=cpu` (the default) keeps it off the GPU; the deploy kit also starts it with no CUDA device visible, so
it cannot take GPU memory. `QA_DEVICE=cuda` needs about 2-5 GB (not measured here). `QA_HEAR=0` leaves the
speech-to-text out (speaker similarity only); `QA_THREADS` limits the CPU threads (default 4: the machine's CPU is
shared with the engines).

STATUS: the speaker model was run on a laptop CPU (25 Nov 2026, docs/v1/MODELS.md); the speech-to-text and the
diarization were NOT run with real models. `V1_STUB=1` starts it without them: it "hears" the text it was given
and reports a fixed similarity, so the backend's scoring path can be tested end to end.
"""
import asyncio
import tempfile
import time
import unicodedata
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from common import STUB, env, gpu_summary, read_mono

DEVICE = env("QA_DEVICE", "cpu")
STT_MODEL = env("QA_STT_MODEL", "large-v3-turbo")
SPK_MODEL = env("QA_SPK_MODEL", "speechbrain/spkrec-ecapa-voxceleb")
DIARIZE = env("QA_DIARIZE", "0") == "1"
HEAR = env("QA_HEAR", "1") == "1"
THREADS = int(env("QA_THREADS", "4"))
ALLOW_NONCOMMERCIAL = env("QA_SPK_ALLOW_NONCOMMERCIAL", "0") == "1"
# Speaker models whose licence was read on the model's own page: id (lower case) -> (licence, commercial use allowed).
SPK_LICENCES = {
    "speechbrain/spkrec-ecapa-voxceleb": ("Apache-2.0", True),
    "jenthe/ecapa2": ("CC-BY-NC-4.0", False),
}
DIAR_MODEL = env("QA_DIAR_MODEL", "pyannote/speaker-diarization-community-1")

app = FastAPI(title="BharatDb v1 QA")
whisper: Any = None
speaker: Any = None
diarizer: Any = None
lock = asyncio.Lock()
state: dict[str, Any] = {"scores": 0, "ms": 0.0, "compares": 0, "compare_ms": 0.0, "speaker_refused": ""}


def speaker_licence(model: str | None = None) -> tuple[str, bool]:
    """(licence, may it be used in a product) for a speaker model; a model nobody checked counts as not allowed."""
    return SPK_LICENCES.get((model or SPK_MODEL).lower(), ("not checked", False))


def speaker_allowed(model: str | None = None) -> bool:
    return speaker_licence(model)[1] or ALLOW_NONCOMMERCIAL


def words(text: str) -> list[str]:
    kept = "".join(c if unicodedata.category(c)[0] in "LMN" else " " for c in text.lower())
    return kept.split()


def words_heard(said: str, heard: str) -> float:
    """Share of the words in `said` that turn up in `heard`: the same word, one with the same first four
    letters, or its letters found in what was heard with the spaces set aside."""
    want, got = words(said), words(heard)
    if not want:
        return 0.0
    have, run = set(got), "".join(got)   # `run`: a word spelled apart or joined still counts (see the backend's heard_share)
    return sum(1 for w in want if w in have or any(w[:4] == g[:4] for g in have) or (len(w) >= 2 and w in run)) / len(want)


def _load() -> None:
    global whisper, speaker, diarizer
    if DEVICE != "cuda":
        import torch
        torch.set_num_threads(max(1, THREADS))
    if HEAR:
        from faster_whisper import WhisperModel
        whisper = WhisperModel(STT_MODEL, device=DEVICE, compute_type="float16" if DEVICE == "cuda" else "int8",
                               cpu_threads=max(1, THREADS))
    if speaker_allowed():
        speaker = _load_speaker()
    else:
        state["speaker_refused"] = (f"{SPK_MODEL} is not loaded: its licence ({speaker_licence()[0]}) is not one that "
                                    "was checked as open to commercial use")
        print("[qa] " + state["speaker_refused"])
    if DIARIZE:
        import os

        from pyannote.audio import Pipeline
        diarizer = Pipeline.from_pretrained(DIAR_MODEL, token=os.environ.get("HF_TOKEN"))


def _load_speaker() -> Any:
    from speechbrain.inference.speaker import EncoderClassifier
    kwargs: dict[str, Any] = {"source": SPK_MODEL, "run_opts": {"device": DEVICE}}
    try:                                    # copy the files instead of linking them: links need rights Windows may not give
        from speechbrain.utils.fetching import LocalStrategy
        kwargs["local_strategy"] = LocalStrategy.COPY
    except ImportError:
        pass
    try:
        return EncoderClassifier.from_hparams(**kwargs)
    except TypeError:                       # an older SpeechBrain without `local_strategy`
        kwargs.pop("local_strategy", None)
        return EncoderClassifier.from_hparams(**kwargs)


@app.on_event("startup")
async def startup() -> None:
    if not STUB:
        await asyncio.get_running_loop().run_in_executor(None, _load)


def _similarity(a: np.ndarray, b: np.ndarray) -> float | None:
    """Cosine similarity of the two speakers' embeddings; None when there is no speaker model or under 0.5 s of sound."""
    if speaker is None or len(a) <= 8000 or len(b) <= 8000:
        return None
    return round(float(np.dot(_embed(a), _embed(b))), 3)


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
                heard = await loop.run_in_executor(None, _hear, path, lang) if whisper is not None else ""
                sim = None
                if ref_raw:
                    sim = await loop.run_in_executor(None, _similarity, read_mono(raw, 16000), read_mono(ref_raw, 16000))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(500, f"scoring failed: {str(e)[:200]}") from e
        finally:
            Path(path).unlink(missing_ok=True)
    ms = (time.perf_counter() - t0) * 1000
    state["scores"] += 1
    state["ms"] += ms
    return {"heard": heard, "backcheck": round(words_heard(text, heard), 3), "similarity": sim, "ms": round(ms)}


@app.post("/similarity")
async def similarity(audio: UploadFile = File(...), ref: UploadFile = File(...)) -> dict[str, Any]:
    """The speaker model alone: how close the voice in `audio` is to the voice in `ref` (cosine, -1 to 1)."""
    raw, ref_raw = await audio.read(), await ref.read()
    if len(raw) < 800 or len(ref_raw) < 800:
        raise HTTPException(422, "empty audio")
    t0 = time.perf_counter()
    if STUB:
        sim: float | None = 1.0 if raw == ref_raw else 0.5
    elif speaker is None:
        raise HTTPException(503, state["speaker_refused"] or "no speaker model is loaded")
    else:
        try:
            async with lock:
                sim = await asyncio.get_running_loop().run_in_executor(
                    None, _similarity, read_mono(raw, 16000), read_mono(ref_raw, 16000))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(500, f"comparison failed: {str(e)[:200]}") from e
    ms = (time.perf_counter() - t0) * 1000
    state["compares"] += 1
    state["compare_ms"] += ms
    return {"similarity": sim, "ms": round(ms), "model": SPK_MODEL}


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


@app.get("/gpu")
async def gpu() -> dict[str, Any]:
    return await asyncio.to_thread(gpu_summary)


@app.get("/health")
async def health() -> dict[str, Any]:
    licence, commercial = speaker_licence()
    loaded = (whisper is not None or not HEAR) and (speaker is not None or bool(state["speaker_refused"]))
    return {"ok": STUB or loaded, "stub": STUB, "device": DEVICE, "model": STT_MODEL if HEAR else None,
            "hear": HEAR and (STUB or whisper is not None),
            "speaker_model": SPK_MODEL, "speaker_licence": licence, "speaker_commercial_use": commercial,
            "speaker_loaded": STUB or speaker is not None, "speaker_refused": state["speaker_refused"] or None,
            "diarization": bool(diarizer) or (STUB and DIARIZE),
            "scores": state["scores"], "score_ms_avg": round(state["ms"] / state["scores"]) if state["scores"] else None,
            "compares": state["compares"],
            "compare_ms_avg": round(state["compare_ms"] / state["compares"]) if state["compares"] else None}
