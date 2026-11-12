"""Smoke test: hit each provider once against the real APIs and print latencies.

    cd backend
    python -m scripts.smoke                       # TTS -> STT REST -> STT stream -> LLM
    python -m scripts.smoke --ref me.wav --consent --vc-langs   # + voice-clone language check (SPEC.md 6.4)

Audio is written to backend/scripts/out/ so you can listen to it.
The STT tests use the TTS output as input (a round trip), so no sample audio is needed.
"""
import argparse
import asyncio
import io
import sys
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import DEFAULT_GLOSSARY, VOICE_BY_LANG, get_settings  # noqa: E402
from app.providers.base import ProviderError, VoiceSpec  # noqa: E402
from app.providers.llm_openai import OpenAILLM  # noqa: E402
from app.providers.stt_gnani import GnaniSTT  # noqa: E402
from app.providers.tts_gnani import GnaniTTS  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
HINDI_LINE = "Namaste doston, aaj hum ek naya game try karenge. Video ko like aur subscribe zaroor karna."
VC_LINES = {
    "hi-IN": "नमस्ते दोस्तों, आज हम एक नया गेम खेलेंगे।",
    "ta-IN": "வணக்கம் நண்பர்களே, இன்று நாம் ஒரு புதிய கேம் விளையாடப் போகிறோம்.",
    "bn-IN": "নমস্কার বন্ধুরা, আজ আমরা একটা নতুন গেম খেলব।",
    "en-IN": "Hello friends, today we are going to play a new game.",
}

rows: list[tuple[str, str, str]] = []


async def timed(name: str, fn: Callable[[], Awaitable[Any]]) -> Any:
    t0 = time.perf_counter()
    try:
        result = await fn()
    except ProviderError as e:
        rows.append((name, "FAIL", str(e)[:120]))
        return None
    rows.append((name, f"{(time.perf_counter() - t0) * 1000:7.0f} ms", ""))
    return result


def to_pcm16k(wav_bytes: bytes) -> bytes:
    data, sr = sf.read(io.BytesIO(wav_bytes), dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    if sr != 16000:
        n = int(len(mono) * 16000 / sr)
        mono = np.interp(np.linspace(0, len(mono) - 1, n), np.arange(len(mono)), mono)
    return (np.clip(mono, -1, 1) * 32767).astype("<i2").tobytes()


async def chunks(pcm: bytes, size: int = 4096) -> AsyncIterator[bytes]:
    for i in range(0, len(pcm), size):
        yield pcm[i:i + size]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", help="5-30 s WAV of a consenting speaker, for the voice-clone check")
    ap.add_argument("--consent", action="store_true", help="the speaker in --ref consented to cloning")
    ap.add_argument("--vc-langs", action="store_true", help="synthesize hi/ta/bn/en with the cloned voice")
    ap.add_argument("--skip-llm", action="store_true")
    a = ap.parse_args()

    s = get_settings()
    OUT.mkdir(exist_ok=True)
    have_gnani = bool(s.gnani_api_key.get_secret_value())
    have_llm = bool(s.llm_base_url and s.llm_model)
    print(f"GNANI_API_KEY set: {have_gnani} | LLM configured: {have_llm} | concurrency gate: {s.gnani_max_concurrency}")

    tts, stt, llm = GnaniTTS(s), GnaniSTT(s), OpenAILLM(s)
    if have_gnani:
        stock: VoiceSpec = {"kind": "stock", "voice": VOICE_BY_LANG["hi-IN"]}
        wav = await timed("tts.synth (hi-IN, Nalini)", lambda: tts.synth(HINDI_LINE, "hi-IN", stock))
        if wav:
            (OUT / "tts_hi.wav").write_bytes(wav)

            async def first_chunk() -> int:
                n = 0
                async for c in tts.synth_stream("Doston, GG! Next round shuru karte hain.", "hi-IN", stock):
                    n += len(c)
                return n
            if await timed("tts.synth_stream total (SSE)", first_chunk) is not None and tts.last_first_chunk_s:
                rows.append(("tts.synth_stream first chunk", f"{tts.last_first_chunk_s * 1000:7.0f} ms", ""))

            clip = OUT / "tts_hi.wav"
            res = await timed("stt.transcribe (REST, indic-auto)", lambda: stt.transcribe(str(clip)))
            if res:
                rows[-1] = (rows[-1][0], rows[-1][1], f"[{res.detected_lang}] {res.text[:70]}")

            async def run_stream() -> list[str]:
                finals, t_proc = [], None
                async for ev in stt.stream(chunks(to_pcm16k(wav)), "indic-auto", pace=True):
                    if ev.kind == "processing":
                        t_proc = time.perf_counter()
                    elif ev.kind == "final":
                        if t_proc:
                            rows.append(("  stream: processing -> final",
                                         f"{(time.perf_counter() - t_proc) * 1000:7.0f} ms", ev.text[:60]))
                        finals.append(ev.text)
                    elif ev.kind == "error":
                        raise ProviderError(f"stt.stream: {ev.message}")
                return finals
            await timed("stt.stream (realtime, paced; incl. audio length)", run_stream)
    else:
        rows.append(("gnani", "SKIP", "GNANI_API_KEY not set"))

    if have_llm and not a.skip_llm:
        lines = ["Bhai ye clutch moment tha!", "Like aur subscribe karna mat bhoolna."]
        out = await timed("llm.translate_batch (2 lines -> ta-IN)",
                          lambda: llm.translate_batch(lines, "ta-IN", DEFAULT_GLOSSARY))
        if out:
            rows[-1] = (rows[-1][0], rows[-1][1], " | ".join(out)[:90])
        out1 = await timed("llm.translate_chunk (fast model -> bn-IN)",
                           lambda: llm.translate_chunk("Ab next round mein full push karenge", "bn-IN",
                                                       DEFAULT_GLOSSARY, []))
        if out1:
            rows[-1] = (rows[-1][0], rows[-1][1], out1[:90])
    elif not a.skip_llm:
        rows.append(("llm", "SKIP", "LLM_BASE_URL / LLM_MODEL not set"))

    if a.vc_langs:
        if not (have_gnani and a.ref):
            rows.append(("vc", "SKIP", "needs GNANI_API_KEY and --ref"))
        else:
            consent_at = datetime.now(timezone.utc).isoformat() if a.consent else None
            emb = await timed("tts.clone_embedding", lambda: tts.clone_embedding(a.ref, consent_at=consent_at))
            if emb:
                clone: VoiceSpec = {"kind": "clone", "embedding": emb}
                for lang, text in VC_LINES.items():
                    audio = await timed(f"vc synth {lang}", lambda t=text, lg=lang: tts.synth(t, lg, clone))
                    if audio:
                        (OUT / f"vc_{lang}.wav").write_bytes(audio)
                print(f"Listen to {OUT}/vc_*.wav and record the verdict in SPEC.md section 16.")

    width = max(len(r[0]) for r in rows)
    print()
    for name, val, note in rows:
        print(f"{name:<{width}}  {val:>10}  {note}")


if __name__ == "__main__":
    asyncio.run(main())
