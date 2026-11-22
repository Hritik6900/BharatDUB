"""v1 voice server (:9041): ONE IndicF5 in one process that speaks several lines in the same forward passes.

v0 runs three engine processes (9001-9003, about 12 GB together) and each speaks one line at a time. This server
holds the model once and gathers the lines that arrive within a few milliseconds into one batch. Same calls as
the v0 engine, so the backend only needs another address:

  POST /ref     multipart: session_id, ref_text, audio  -> the voice to copy
  POST /tts     json {session_id, text, lang, speed, fmt, nfe}  -> audio, headers as the v0 engine's plus X-Batch
  GET  /health

STATUS: the batched path was written from the library's interface (`CFM.sample` with a padded batch and `lens`)
and has NOT been run on a GPU. It is guarded: any error in a batch speaks those lines one at a time through the
library's own `infer_process` (the path v0 uses), and after three such errors batching is switched off for this
process. Compare its audio with the v0 engine's before it replaces them (docs/v1/NEEDS_APPROVAL.md).

  V1_STUB=1 uvicorn tts_server:app --host 127.0.0.1 --port 9041     # no model, no GPU: tones of the right length
  NFE=12 BATCH_MAX=4 BATCH_WAIT_MS=15 uvicorn tts_server:app --host 127.0.0.1 --port 9041
"""
import asyncio
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from common import SR, STUB, encode, env, letters, stub_wave

REPO = env("TTS_REPO", "ai4bharat/IndicF5")
REVISION = env("TTS_REVISION", "main")          # pin to the full commit hash when first deployed
NFE = int(env("NFE", "12"))
BF16 = env("PRECISION", "bf16") == "bf16"
BATCH_MAX = int(env("BATCH_MAX", "4"))
BATCH_WAIT_MS = float(env("BATCH_WAIT_MS", "15"))
REF_DIR = Path(env("REF_DIR", "/tmp/voice_refs_v1"))
HOP, CFG, SWAY = 256, 2.0, -1.0                 # the model's mel hop and the library's sampling defaults

app = FastAPI(title="BharatDb v1 voice server")
model: Any = None
vocoder: Any = None
refs: dict[str, dict[str, Any]] = {}            # session -> {"audio": path, "text": str, "version": int, "mel": tensor}
queue: "asyncio.Queue[Job]" = asyncio.Queue()
state = {"batch_errors": 0, "batching": BATCH_MAX > 1, "batches": 0, "lines": 0, "largest": 0}


@dataclass
class Job:
    ref: dict[str, Any]
    text: str
    speed: float
    nfe: int
    done: "asyncio.Future[np.ndarray]"
    batch: int = 1
    t0: float = field(default_factory=time.perf_counter)


def quiet(*_a: Any, **_k: Any) -> None:
    pass


def _load() -> None:
    global model, vocoder
    import torch  # noqa: F401
    from f5_tts.infer.utils_infer import load_model, load_vocoder
    from f5_tts.model import DiT
    from huggingface_hub import snapshot_download
    from safetensors.torch import load_file
    snap = Path(snapshot_download(REPO, revision=REVISION, allow_patterns=["model.safetensors", "checkpoints/vocab.txt"]))
    vocoder = load_vocoder(vocoder_name="vocos", is_local=False, device="cuda")
    model = load_model(DiT, dict(dim=1024, depth=22, heads=16, ff_mult=2, text_dim=512, conv_layers=4),
                       mel_spec_type="vocos", vocab_file=str(snap / "checkpoints" / "vocab.txt"), device="cuda")
    weights = load_file(str(snap / "model.safetensors"), device="cuda")
    for target, prefix in ((model, "ema_model._orig_mod."), (vocoder, "vocoder._orig_mod.")):
        part = {k[len(prefix):]: v for k, v in weights.items() if k.startswith(prefix)}
        target.load_state_dict(part, strict=False)
    model.eval()


def _speed(ref_text: str, text: str, speed: float) -> float:
    """The library sizes a line by UTF-8 bytes; letters are the fair measure in every script (as the v0 engine)."""
    by_bytes = len(text.encode("utf-8")) / max(1, len(ref_text.encode("utf-8")))
    return speed * by_bytes / (letters(text) / letters(ref_text))


def _one(job: Job) -> np.ndarray:
    """One line through the library's own path: exactly what the v0 engine does."""
    if STUB:
        return stub_wave(job.text, job.speed)
    import torch
    from f5_tts.infer.utils_infer import infer_process
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16, enabled=BF16):
        wave, _sr, _spec = infer_process(job.ref["audio"], job.ref["text"], job.text, model, vocoder,
                                         mel_spec_type="vocos", nfe_step=job.nfe or NFE, show_info=quiet,
                                         speed=_speed(job.ref["text"], job.text, job.speed), device="cuda")
    return np.asarray(wave, dtype=np.float32)


def _ref_mel(ref: dict[str, Any]) -> Any:
    """The sample as the model's mel frames (1, n, d), made once per voice."""
    if ref.get("mel") is None:
        import torch
        import torchaudio
        audio, sr = torchaudio.load(ref["audio"])
        audio = audio.mean(dim=0, keepdim=True)
        rms = torch.sqrt(torch.mean(torch.square(audio)))
        if rms < 0.1:                                   # the library lifts a quiet sample to this level
            audio = audio * 0.1 / rms
            ref["gain"] = float(rms / 0.1)
        if sr != SR:
            audio = torchaudio.transforms.Resample(sr, SR)(audio)
        ref["mel"] = model.mel_spec(audio.to("cuda")).permute(0, 2, 1)
    return ref["mel"]


def _batch(jobs: list[Job]) -> list[np.ndarray]:
    """Several lines in the same forward passes: samples padded to the longest, each with its own length."""
    if STUB:
        return [stub_wave(j.text, j.speed) for j in jobs]
    import torch
    from f5_tts.model.utils import convert_char_to_pinyin
    mels = [_ref_mel(j.ref)[0] for j in jobs]
    lens = torch.tensor([m.shape[0] for m in mels], device="cuda")
    cond = torch.zeros(len(jobs), int(lens.max()), mels[0].shape[-1], device="cuda", dtype=mels[0].dtype)
    for i, m in enumerate(mels):
        cond[i, : m.shape[0]] = m
    texts = convert_char_to_pinyin([j.ref["text"] + " " + j.text for j in jobs])
    durations = torch.tensor([
        int(m.shape[0] + m.shape[0] / max(1, len(j.ref["text"].encode("utf-8"))) * len(j.text.encode("utf-8"))
            / _speed(j.ref["text"], j.text, j.speed)) for m, j in zip(mels, jobs)], device="cuda")
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16, enabled=BF16):
        out, _ = model.sample(cond=cond, text=texts, duration=durations, lens=lens, steps=max(j.nfe for j in jobs) or NFE,
                              cfg_strength=CFG, sway_sampling_coef=SWAY)
        waves = []
        for i, j in enumerate(jobs):
            mel = out[i: i + 1, int(lens[i]): int(durations[i])].float().permute(0, 2, 1)
            wave = vocoder.decode(mel).squeeze().float().cpu().numpy()
            waves.append(np.asarray(wave * j.ref.get("gain", 1.0), dtype=np.float32))
    return waves


async def _worker() -> None:
    loop = asyncio.get_running_loop()
    while True:
        jobs = [await queue.get()]
        if state["batching"]:
            deadline = time.perf_counter() + BATCH_WAIT_MS / 1000
            while len(jobs) < BATCH_MAX:
                left = deadline - time.perf_counter()
                if left <= 0:
                    break
                try:
                    jobs.append(await asyncio.wait_for(queue.get(), left))
                except TimeoutError:
                    break
        waves: list[Any] | None = None
        if len(jobs) > 1:
            try:
                waves = await loop.run_in_executor(None, _batch, jobs)
                state["batches"] += 1
            except Exception as e:  # noqa: BLE001 - these lines are spoken one at a time instead
                state["batch_errors"] += 1
                print(f"[tts-server] batch of {len(jobs)} failed ({str(e)[:160]}); speaking one at a time")
                if state["batch_errors"] >= 3:
                    state["batching"] = False
                    print("[tts-server] batching switched off for this process")
        if waves is None:
            waves = []
            for j in jobs:
                try:
                    waves.append(await loop.run_in_executor(None, _one, j))
                except Exception as e:  # noqa: BLE001
                    waves.append(e)
        state["lines"] += len(jobs)
        state["largest"] = max(state["largest"], len(jobs))
        for j, w in zip(jobs, waves):
            j.batch = len(jobs)
            if j.done.done():
                continue
            if isinstance(w, Exception):
                j.done.set_exception(w)
            else:
                j.done.set_result(w)


@app.on_event("startup")
async def startup() -> None:
    REF_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    if not STUB:
        await asyncio.get_running_loop().run_in_executor(None, _load)
    asyncio.create_task(_worker())
    print(f"[tts-server] ready in {time.perf_counter() - t0:.1f} s, stub={STUB}, batch up to {BATCH_MAX}")


@app.post("/ref")
async def set_ref(session_id: str = Form(...), ref_text: str = Form(...), audio: UploadFile = File(...)) -> dict[str, Any]:
    raw = await audio.read()
    if len(raw) < 2000 or not ref_text.strip():
        raise HTTPException(422, "need a voice sample and the words spoken in it")
    version = refs.get(session_id, {}).get("version", 0) + 1
    path = REF_DIR / f"{os.getpid()}-{abs(hash(session_id))}-{version}.wav"
    path.write_bytes(raw)
    processed, text = str(path), ref_text.strip()
    if not STUB:
        from f5_tts.infer.utils_infer import preprocess_ref_audio_text
        try:
            processed, text = await asyncio.get_running_loop().run_in_executor(
                None, lambda: preprocess_ref_audio_text(str(path), ref_text.strip(), show_info=quiet))
        except Exception as e:  # noqa: BLE001 - an unreadable sample must not take the server down
            raise HTTPException(422, f"could not read the sample: {str(e)[:160]}") from e
    refs[session_id] = {"audio": processed, "text": text, "version": version, "mel": None}
    while len(refs) > 300:                      # the v0 engines keep every voice until restarted; this one does not
        refs.pop(next(iter(refs)))
    return {"ok": True, "session_id": session_id, "version": version}


class Line(BaseModel):
    session_id: str
    text: str
    lang: str = ""
    speed: float = 1.0
    fmt: str = "pcm"
    nfe: int = 0


@app.post("/tts")
async def tts(req: Line) -> Response:
    ref = refs.get(req.session_id)
    if not ref:
        raise HTTPException(409, "no voice sample for this session: POST /ref first")
    if not req.text.strip():
        raise HTTPException(422, "empty text")
    job = Job(ref, req.text.strip(), max(0.4, min(1.5, req.speed)), max(0, min(64, req.nfe)),
              asyncio.get_running_loop().create_future())
    await queue.put(job)
    try:
        wave = await job.done
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"synthesis failed: {str(e)[:200]}") from e
    ms = (time.perf_counter() - job.t0) * 1000
    fmt = req.fmt if req.fmt in ("opus", "mp3") else "pcm"
    return Response(content=encode(wave, fmt), media_type="application/octet-stream", headers={
        "X-Synth-Ms": f"{ms:.0f}", "X-Sample-Rate": str(SR), "X-Format": fmt, "X-Ref-Version": str(ref["version"]),
        "X-Speed": str(job.speed), "X-Audio-Ms": f"{wave.size / SR * 1000:.0f}", "X-Batch": str(job.batch)})


@app.get("/health")
async def health() -> dict[str, Any]:
    gpu = 0.0
    if not STUB and model is not None:
        import torch
        gpu = round(torch.cuda.memory_allocated() / 1e9, 2)
    return {"ok": STUB or model is not None, "model": REPO, "revision": REVISION, "stub": STUB, "nfe": NFE,
            "voices": len(refs), "gpu_gb": gpu, "batching": state["batching"], "batch_max": BATCH_MAX,
            "lines": state["lines"], "batches": state["batches"], "largest_batch": state["largest"],
            "batch_errors": state["batch_errors"]}
