"""Runs ON the GPU machine: IndicF5 as a small voice-copy server for Live and Streamer Mode.

  NFE=12 python -m uvicorn voice_engine_live:app --host 127.0.0.1 --port 9001     (start_live.sh runs three of these)

  POST /ref     multipart: session_id, ref_text, audio (3-10 s of speech, any sample rate)  -> the voice to copy
  POST /tts     json: {session_id, text, lang, speed, fmt}  -> audio (24 kHz mono; raw PCM16, or fmt = "mp3" | "opus")
                headers: X-Synth-Ms, X-Encode-Ms, X-Sample-Rate, X-Format, X-Ref-Version, X-Speed
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
# 1 = both halves of the guidance in one batch (see BatchedGuidance); 0 = the library's two passes per step.
# Measured 21 Nov 2026, bf16, 10 steps: one line 742 ms -> 366 ms, GPU busy 39% -> 52%; log-mel distance from the
# fp32 two-pass audio 0.4-1.2 dB (two-pass bf16: 0.5-0.6 dB). In fp32 the two ways agree to -37..-49 dB.
BATCH_CFG = os.environ.get("CFG_BATCH", "1") == "1"
SR = 24000
REF_DIR = Path(os.environ.get("REF_DIR", "/tmp/voice_refs"))

app = FastAPI(title="Bharat Dub voice engine")
model = None
vocoder = None
refs: dict[str, dict] = {}          # session_id -> {"audio": processed path, "text": str, "version": int}
lock = asyncio.Lock()               # one line at a time on this process


def quiet(*_a, **_k) -> None:
    pass


class BatchedGuidance(torch.nn.Module):
    """Both halves of classifier-free guidance in one pass through the network.

    The library's sampler calls the network twice on every step: once with the voice sample and the text, once with both
    dropped, and mixes the two results. This wrapper answers the first call by running both as one batch of two and
    hands the second result back when the sampler asks for it. The text is the same on every step of a line, so its
    embedding is made once per line instead of twice per step. Same arithmetic, half the network calls.
    Anything it does not recognise (a batch, a mask, only one of the two dropped) goes to the network unchanged.
    """

    def __init__(self, dit: torch.nn.Module) -> None:
        super().__init__()
        self.dit = dit
        self._null = None    # the "dropped" half of the last batched call, waiting to be asked for
        self._text = None    # the text tensor the cached embedding belongs to (kept, so its identity cannot be reused)
        self._embed = None

    def forward(self, x, cond, text, time, drop_audio_cond, drop_text, mask=None):  # noqa: ANN001, ANN201
        d = self.dit
        if drop_audio_cond and drop_text and self._null is not None:
            out, self._null = self._null, None
            return out
        self._null = None
        if drop_audio_cond or drop_text or mask is not None or x.shape[0] != 1:
            return d(x=x, cond=cond, text=text, time=time, drop_audio_cond=drop_audio_cond, drop_text=drop_text, mask=mask)
        seq_len = x.shape[1]
        t = d.time_embed(time.repeat(2) if time.ndim == 0 else time.expand(2))
        if self._text is not text or self._embed.shape[1] != seq_len:
            self._embed = torch.cat([d.text_embed(text, seq_len, drop_text=False), d.text_embed(text, seq_len, drop_text=True)])
            self._text = text
        h = d.input_embed(x.expand(2, -1, -1), torch.cat([cond, torch.zeros_like(cond)]), self._embed, drop_audio_cond=False)
        rope = d.rotary_embed.forward_from_seq_len(seq_len)
        residual = h
        for block in d.transformer_blocks:
            h = block(h, t, mask=None, rope=rope)
        if d.long_skip_connection is not None:
            h = d.long_skip_connection(torch.cat((h, residual), dim=-1))
        out = d.proj_out(d.norm_out(h, t))
        self._null = out[1:]
        return out[:1]


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
    if BATCH_CFG:
        model.transformer = BatchedGuidance(model.transformer)
    # Warm up on one of the repo's own prompts, so the first real line is not the slow one.
    wav = sorted(glob.glob(str(snap / "prompts" / "*.wav")))
    if wav:
        audio, text = preprocess_ref_audio_text(wav[0], "नमस्ते, यह एक परीक्षण है।", show_info=quiet)
        _synth(audio, text, "नमस्ते।", 1.0)


def _letters(text: str) -> int:
    return max(1, sum(1 for ch in text if not ch.isspace()))


def _synth(ref_audio: str, ref_text: str, text: str, speed: float, nfe: int = 0) -> np.ndarray:
    # The library sizes the new audio by UTF-8 bytes: (sample seconds) x (new bytes / sample bytes). An Indic letter is
    # 3 bytes and a Latin one is 1, so a sample transcribed in Latin letters (Hinglish) made Tamil lines three times too
    # long (measured: 9 words -> 18 s). Letters are a fair measure in every script, so the speed is corrected to them.
    by_bytes = len(text.encode("utf-8")) / max(1, len(ref_text.encode("utf-8")))
    by_letters = _letters(text) / _letters(ref_text)
    speed = speed * by_bytes / by_letters
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16, enabled=BF16):
        wave, _sr, _spec = infer_process(ref_audio, ref_text, text, model, vocoder, mel_spec_type="vocos",
                                         nfe_step=nfe or NFE, show_info=quiet, speed=speed, device="cuda")
    return np.asarray(wave, dtype=np.float32)


def _encode(wave: np.ndarray, fmt: str) -> bytes:
    peak = float(np.max(np.abs(wave))) if wave.size else 0.0
    if peak > 0.98:
        wave = wave * (0.98 / peak)
    pcm = (wave * 32767.0).astype("<i2")
    if fmt == "pcm":
        return pcm.tobytes()
    buf = io.BytesIO()
    if fmt == "mp3":
        # Measured 21 Nov 2026 on 3 s lines: MP3 at this setting 14.0 KB, 30 ms to make, 0.48 dB from the line on a
        # log-mel scale; Opus 13.4 KB, 144 ms, 0.73 dB. Same size, so the same trips over the network, 113 ms sooner.
        sf.write(buf, pcm, SR, format="MP3", subtype="MPEG_LAYER_III", compression_level=0.7, bitrate_mode="VARIABLE")
    else:
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
    fmt: str = "pcm"     # "mp3" or "opus": about a tenth of the bytes of raw PCM
    nfe: int = 0         # 0 = this process's NFE; set only to compare settings


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
            wave = await asyncio.get_running_loop().run_in_executor(None, _synth, ref["audio"], ref["text"], req.text, speed, max(0, min(64, req.nfe)))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(500, f"synthesis failed: {str(e)[:200]}") from e
        ms = (time.perf_counter() - t0) * 1000
    fmt = req.fmt if req.fmt in ("opus", "mp3") else "pcm"
    t0 = time.perf_counter()
    body = _encode(wave, fmt)
    return Response(content=body, media_type="application/octet-stream", headers={
        "X-Synth-Ms": f"{ms:.0f}", "X-Encode-Ms": f"{(time.perf_counter() - t0) * 1000:.0f}",
        "X-Sample-Rate": str(SR), "X-Format": fmt, "X-Ref-Version": str(ref["version"]),
        "X-Speed": str(speed), "X-Audio-Ms": f"{wave.size / SR * 1000:.0f}"})


@app.get("/health")
async def health() -> dict:
    return {"ok": model is not None, "nfe": NFE, "bf16": BF16, "batched_guidance": BATCH_CFG, "voices": len(refs),
            "gpu_gb": round(torch.cuda.memory_allocated() / 1e9, 2) if model is not None else 0}
