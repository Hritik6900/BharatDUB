"""Speech-to-text on our own GPU, for the all-GPU mode (`AI_MODE=gpu`). Listens on 127.0.0.1 only.

  STT_MODEL=models/apex-ct2 .venv_stt/bin/python -m uvicorn stt_engine:app --host 127.0.0.1 --port 9030    (start_stt.sh)

Model: Oriserve/Whisper-Hindi2Hinglish-Apex (Apache-2.0), converted for CTranslate2. It writes Hindi and Hinglish in
Latin letters, English words as they are spelt ("ise ham machine mein dedh ghante pakaate hain").

  POST /stt      multipart: audio (any format soundfile reads), lang   -> {text, ms, audio_ms}
  WS   /stream   binary PCM16 mono 16 kHz in; JSON events out, the same ones the hosted realtime service sends, so the
                 backend reads both with one parser:
                   connected, speech_start, partial_transcript {text, stable_text}, speech_end {t_ms}, final_transcript
  GET  /health

Whisper is not a streaming model. While somebody speaks, the utterance so far is decoded again every `interval`;
a word counts as settled (`stable_text`) once two decodes in a row agree on it, and settled words are never taken
back. Silero VAD finds where speech starts and stops. An utterance that runs past `MAX_SPEECH_S` without a pause is
closed at the quietest recent moment, so one decode never grows past a few seconds of audio.
"""
import asyncio
import glob
import io
import json
import os
import site
import time
from typing import Any

for _sp in site.getsitepackages():   # CTranslate2 needs cuDNN/cuBLAS, which come with the torch wheels
    for _d in glob.glob(_sp + "/nvidia/*/lib"):
        os.environ["LD_LIBRARY_PATH"] = _d + ":" + os.environ.get("LD_LIBRARY_PATH", "")

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
import torch  # noqa: E402
from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect  # noqa: E402
from faster_whisper import WhisperModel  # noqa: E402
from silero_vad import load_silero_vad  # noqa: E402

MODEL = os.environ.get("STT_MODEL", "models/apex-ct2")
MAX_SPEECH_S = float(os.environ.get("MAX_SPEECH_S", "9"))
SR = 16000
WIN = 512                 # Silero's window: 32 ms
PRE_ROLL = int(0.3 * SR)  # audio kept from before speech was noticed

app = FastAPI()
model: WhisperModel | None = None
gpu = asyncio.Lock()      # one decode at a time; each takes 0.1-0.2 s
stats = {"decodes": 0, "decode_ms": 0.0, "streams": 0}


@app.on_event("startup")
def _load() -> None:
    global model
    t0 = time.perf_counter()
    model = WhisperModel(MODEL, device="cuda", compute_type="float16")
    _decode(np.zeros(SR, dtype=np.float32), "")   # first call compiles kernels
    print(f"[stt-engine] {MODEL} ready in {time.perf_counter() - t0:.1f} s")


def _decode(audio: np.ndarray, hint: str) -> str:
    assert model is not None
    t0 = time.perf_counter()
    segs, _info = model.transcribe(audio, language="hi", beam_size=1, temperature=0.0, without_timestamps=True,
                                   condition_on_previous_text=False, initial_prompt=hint or None,
                                   no_speech_threshold=0.6, log_prob_threshold=-1.0, compression_ratio_threshold=2.4)
    text = " ".join(s.text.strip() for s in segs).strip()
    stats["decodes"] += 1
    stats["decode_ms"] += (time.perf_counter() - t0) * 1000
    return text


async def decode(audio: np.ndarray, hint: str = "") -> str:
    async with gpu:
        return await asyncio.get_running_loop().run_in_executor(None, _decode, audio, hint)


def _bare(w: str) -> str:
    return "".join(ch for ch in w.lower() if ch.isalnum())


def agreed(prev: list[str], now: list[str]) -> int:
    """How many words two decodes share from the start, ignoring case and punctuation."""
    k = 0
    while k < len(prev) and k < len(now) and _bare(prev[k]) == _bare(now[k]):
        k += 1
    return k


@app.get("/health")
def health() -> dict[str, Any]:
    n = max(1, stats["decodes"])
    return {"ok": model is not None, "model": MODEL, "streams": stats["streams"], "decodes": stats["decodes"],
            "decode_ms_avg": round(stats["decode_ms"] / n)}


@app.post("/stt")
async def stt(audio: UploadFile = File(...), lang: str = Form("hi-IN"), hint: str = Form("")) -> dict[str, Any]:
    raw = await audio.read()
    x, sr = sf.read(io.BytesIO(raw), dtype="float32", always_2d=False)
    if x.ndim > 1:
        x = x.mean(axis=1)
    if sr != SR:
        import torchaudio
        x = torchaudio.functional.resample(torch.from_numpy(np.ascontiguousarray(x)), sr, SR).numpy()
    t0 = time.perf_counter()
    text = await decode(x, hint) if len(x) >= SR // 10 else ""
    return {"text": text, "ms": round((time.perf_counter() - t0) * 1000), "audio_ms": round(len(x) / SR * 1000)}


@app.websocket("/stream")
async def stream(ws: WebSocket) -> None:
    await ws.accept()
    q = ws.query_params
    min_silence = int(q.get("min_silence_ms", "500")) / 1000
    interval = int(q.get("partial_interval_ms", "300")) / 1000
    max_speech = float(q.get("max_speech_s", MAX_SPEECH_S))
    hint = q.get("hint", "")
    vad = load_silero_vad()     # its own state per stream; runs on the CPU in under 1 ms a window
    stats["streams"] += 1

    buf = np.zeros(0, dtype=np.float32)       # audio not yet through the VAD
    ring = np.zeros(0, dtype=np.float32)      # the last PRE_ROLL of audio while nobody speaks
    utt = np.zeros(0, dtype=np.float32)       # the utterance being spoken
    probs: list[float] = []                   # VAD probability of each window of `utt`
    clock = 0                                 # samples received: the stream clock
    speaking, silent, uid_n = False, 0.0, 0
    uid = ""
    prev: list[str] = []
    settled: list[str] = []
    last_partial_at = 0.0
    pending: asyncio.Task[None] | None = None
    send_lock = asyncio.Lock()

    async def send(obj: dict[str, Any]) -> None:
        async with send_lock:
            await ws.send_text(json.dumps(obj, ensure_ascii=False))

    async def partial(audio: np.ndarray, my_uid: str) -> None:
        nonlocal prev, settled
        words = (await decode(audio, hint)).split()
        if my_uid != uid or not words:   # the utterance ended while this was decoding
            return
        k = agreed(prev, words)
        prev = words
        if k > len(settled):
            settled = settled + words[len(settled):k]
        await send({"type": "partial_transcript", "utterance_id": my_uid, "text": " ".join(words),
                    "stable_text": " ".join(settled)})

    async def finish(audio: np.ndarray, my_uid: str, t_ms: int) -> None:
        text = await decode(audio, hint)
        await send({"type": "final_transcript", "utterance_id": my_uid, "text": text, "is_final": True,
                    "audio_duration_ms": round(len(audio) / SR * 1000), "t_ms": t_ms})

    def begin() -> None:
        nonlocal speaking, silent, uid, uid_n, prev, settled, last_partial_at
        uid_n += 1
        uid, speaking, silent, prev, settled = f"u{uid_n}", True, 0.0, [], []
        last_partial_at = time.perf_counter()

    finals: list[asyncio.Task[None]] = []
    await send({"type": "connected", "model": MODEL, "partials_enabled": True})
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("text"):
                if '"commit"' in msg["text"] and speaking and len(utt) > SR // 5:
                    await send({"type": "speech_end", "utterance_id": uid, "t_ms": round(clock / SR * 1000)})
                    finals.append(asyncio.create_task(finish(utt.copy(), uid, round(clock / SR * 1000))))
                    speaking, utt, probs = False, np.zeros(0, dtype=np.float32), []
                continue
            data = msg.get("bytes") or b""
            x = np.frombuffer(data[: len(data) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0
            clock += len(x)
            buf = np.concatenate([buf, x])
            while len(buf) >= WIN:
                w, buf = buf[:WIN], buf[WIN:]
                p = float(vad(torch.from_numpy(w), SR).item())
                if not speaking:
                    ring = np.concatenate([ring, w])[-PRE_ROLL:]
                    if p >= 0.5:
                        begin()
                        utt, probs = ring.copy(), [p]
                        ring = np.zeros(0, dtype=np.float32)
                        await send({"type": "speech_start", "utterance_id": uid})
                    continue
                utt = np.concatenate([utt, w])
                probs.append(p)
                silent = silent + WIN / SR if p < 0.35 else 0.0
                over = len(utt) / SR >= max_speech
                if silent >= min_silence or over:
                    cut = len(utt)
                    if over and silent < min_silence:
                        # No pause in sight: close the utterance at the quietest window of the last 0.6 s (words
                        # older than that may already be settled and given out).
                        tail = probs[-19:]
                        back = len(tail) - 1 - int(np.argmin(tail))
                        cut = len(utt) - back * WIN
                    done, rest = utt[:cut], utt[cut:]
                    t_ms = round((clock - len(buf) - len(rest)) / SR * 1000)
                    await send({"type": "speech_end", "utterance_id": uid, "t_ms": t_ms})
                    finals.append(asyncio.create_task(finish(done.copy(), uid, t_ms)))
                    speaking = False
                    if over and silent < min_silence:   # the speaker is still talking: the next utterance starts here
                        begin()
                        utt, probs = rest.copy(), probs[len(probs) - len(rest) // WIN:]
                        await send({"type": "speech_start", "utterance_id": uid})
                    else:
                        utt, probs = np.zeros(0, dtype=np.float32), []
                    continue
            if speaking and time.perf_counter() - last_partial_at >= interval and len(utt) >= SR // 2 \
                    and (pending is None or pending.done()):
                last_partial_at = time.perf_counter()
                pending = asyncio.create_task(partial(utt.copy(), uid))
            finals = [t for t in finals if not t.done()]
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        stats["streams"] -= 1
        for t in finals:
            try:
                await asyncio.wait_for(t, 3)
            except Exception:  # noqa: BLE001
                pass
