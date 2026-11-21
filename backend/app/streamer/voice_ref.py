"""The streamer's voice for our GPU engine, built once from the recording they made with consent.

The engine copies pace and words from a short sample, so the sample decides how good every later line is
(measured 2026-11-14: 47% to 86% of words heard back, depending on the sample alone). So up to three cuts of
the recording are tried, each transcribed from the exact cut, turned into a voice, and scored by having that
voice say a known sentence that Prisma hears back. The best one is kept on disk and sent to the engines when
a session starts, so the first phrase of a stream is already in the streamer's voice.
"""
import asyncio
import logging
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from app.config import get_settings
from app.live.pipeline import GPU_GOOD_SCORE, score_voice, speech_cut
from app.providers import get_gpu_voice, get_stt
from app.shared import audio_utils as au

log = logging.getLogger("streamer")
FRAME = 1024          # bytes: 32 ms of 16 kHz PCM16, the frame size speech_cut works in
MAX_CUTS = 3


def engine_voice_id(profile_id: str) -> str:
    """The name of this profile's voice on the GPU engines."""
    return f"voice-{profile_id}"


async def sample_text(p: dict[str, Any], path: Path, src_lang: str = "hi-IN", *, stt: Any = None, store: Any = None) -> str:
    """The text to send with a profile's voice sample: the stored one, unless it no longer belongs to the file.

    The engine takes its pace from the sample and the sample's text together. A text written for a 15.7 s cut, sent
    with a 9 s cut of the same recording, made every line about twice as fast (measured 2026-11-21: 53% of the words
    heard back in Punjabi, 91% with the right text). The stored length is what ties the two together: when the file
    is a different length, the file is transcribed again and the profile is corrected.
    """
    try:
        secs = sf.info(str(path)).duration
    except Exception:  # noqa: BLE001 - no file to check: the caller's own error handling takes it from here
        return str(p["ref_text"])
    stored = p.get("ref_seconds")
    if stored is not None and abs(float(stored) - secs) <= 0.5:
        return str(p["ref_text"])
    try:
        heard = (await (stt or get_stt()).transcribe(str(path), src_lang)).text.strip()
    except Exception as e:  # noqa: BLE001 - fail soft: the stored text is still the best there is
        log.warning("voice reference %s: could not re-read the sample (%s)", p.get("id"), e)
        return str(p["ref_text"])
    if len(heard.split()) < 4:
        return str(p["ref_text"])
    log.warning("voice reference %s: stored text was for %s s, the file is %.1f s; text taken from the file again",
                p.get("id"), stored, secs)
    if store is None:
        from app.db import get_store
        store = get_store()
    await store.update("voice_profiles", p["id"], {"ref_text": heard, "ref_seconds": round(secs, 1)})
    return heard


async def _clean(wav44: Path, out: Path) -> bool:
    """Take game sound and music out of the recording (Demucs on the GPU machine), when that is available."""
    url = get_settings().gpu_separate_url
    if not url:
        return False
    from app.studio.stages.separate import _separate_gpu
    rest = out.with_name(out.stem + "_rest.wav")
    try:
        await asyncio.to_thread(_separate_gpu, url, wav44, out, rest)
        return True
    except Exception as e:  # noqa: BLE001 - the recording is used as it is
        log.warning("voice reference: cleaning failed (%s)", e)
        out.unlink(missing_ok=True)
        return False
    finally:
        rest.unlink(missing_ok=True)


async def build(profile_id: str, wav44: Path, *, consent_at: str | None, src_lang: str, check_lang: str,
                out_dir: Path) -> dict[str, Any] | None:
    """Make and score the engine voice for a profile. Returns what to store on the profile, or None when the
    engine is off or no usable cut was found. Refuses (inside the provider) without recorded consent."""
    gpu, stt = get_gpu_voice(), get_stt()
    if not gpu.enabled:
        return None
    t0 = time.perf_counter()
    tmp = Path(tempfile.gettempdir())
    vocals = tmp / f"bd_ref_{profile_id}_vocals.wav"
    cleaned = await _clean(wav44, vocals)
    wav16 = tmp / f"bd_ref_{profile_id}_16k.wav"
    try:
        await asyncio.to_thread(au.extract_wav, vocals if cleaned else wav44, wav16, 16000)
        pcm = sf.read(wav16, dtype="int16", always_2d=False)[0].tobytes()
    finally:
        vocals.unlink(missing_ok=True)
        wav16.unlink(missing_ok=True)
    frames = [pcm[i:i + FRAME] for i in range(0, len(pcm) - FRAME + 1, FRAME)]
    # Cuts ending at the end, at two thirds and at one third of the recording. The end comes first: by then the
    # consent sentence has been read and the speaker is talking the way they do on stream.
    ends = sorted({len(frames), len(frames) * 2 // 3, len(frames) // 3}, reverse=True)[:MAX_CUTS]
    best: dict[str, Any] | None = None
    tried = 0
    for i, end in enumerate(ends):
        cut = speech_cut(frames[:end])
        if cut is None:
            continue
        ref = out_dir / f"{profile_id}_ref{i}.wav"
        audio = np.frombuffer(cut, dtype="<i2").astype(np.float32) / 32768.0
        audio = np.concatenate([audio, np.zeros(4000, dtype=np.float32)])  # a clean stop: 0.25 s of silence
        await asyncio.to_thread(au.write_wav, ref, audio, 16000)
        try:
            text = (await stt.transcribe(str(ref), src_lang)).text.strip()
            if len(text.split()) < 4:
                ref.unlink(missing_ok=True)
                continue
            cand = f"{engine_voice_id(profile_id)}-c{i}"
            await gpu.set_ref(cand, str(ref), text, consent_at=consent_at)
            score = await score_voice(gpu, stt, cand, check_lang)
        except Exception as e:  # noqa: BLE001 - this cut is not usable; the next one is tried
            log.warning("voice reference: cut %d failed (%s)", i, e)
            ref.unlink(missing_ok=True)
            continue
        tried += 1
        this = {"ref": ref, "ref_text": text, "ref_score": score, "ref_seconds": round(len(audio) / 16000, 1)}
        if best is None or (score or 0.0) > (best["ref_score"] or 0.0):
            if best:
                best["ref"].unlink(missing_ok=True)
            best = this
        else:
            ref.unlink(missing_ok=True)
        if (score or 0.0) >= GPU_GOOD_SCORE:
            break
    if best is None:
        return None
    final = out_dir / f"{profile_id}_ref.wav"
    best.pop("ref").replace(final)
    return {**best, "ref_path": final.name, "ref_cleaned": cleaned, "ref_cuts_tried": tried,
            "ref_build_s": round(time.perf_counter() - t0, 1)}
