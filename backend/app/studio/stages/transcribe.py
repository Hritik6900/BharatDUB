"""Stage 5: Prisma REST per segment. Cached by the clip's audio hash: STT never re-runs on the same audio."""
import asyncio
from pathlib import Path

import numpy as np

from app.providers.base import STT, ProviderError
from app.shared import audio_utils as au
from app.shared import cache

STT_MODEL = "prisma-v3.0"


def cut_clips(vocals16k: np.ndarray, segs: list[tuple[float, float]], clip_dir: Path) -> list[Path]:
    clip_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, (s, e) in enumerate(segs):
        p = clip_dir / f"src_{i:03}.wav"
        au.write_wav(p, vocals16k[int(s * 16000):int(e * 16000)], 16000)
        paths.append(p)
    return paths


async def transcribe_clip(stt: STT, clip: Path, lang: str, keyterms: list[str],
                          usage: dict, warnings: list[str]) -> dict:
    key = au.cache_key(au.sha256_file(clip), lang, STT_MODEL)
    hit = cache.get_json("transcribe", key)
    if hit is not None:
        usage["stt_cache_hits"] = usage.get("stt_cache_hits", 0) + 1
        return hit
    result: dict = {"text": "", "lang": None}
    for try_lang in dict.fromkeys([lang, "hi-IN"]):  # spec: 1 retry (in provider), then hi-IN
        try:
            r = await stt.transcribe(str(clip), try_lang, keyterms=keyterms)
            result = {"text": r.text, "lang": r.detected_lang or (try_lang if try_lang != "indic-auto" else None)}
            usage["stt_calls"] = usage.get("stt_calls", 0) + 1
            usage["stt_audio_s"] = round(usage.get("stt_audio_s", 0.0) + au.duration_s(clip), 2)
            cache.put_json("transcribe", key, result)
            return result
        except ProviderError as e:
            last = str(e)
    warnings.append(f"Could not transcribe {clip.name}: {last[:160]}")
    return result


async def transcribe_all(stt: STT, clips: list[Path], lang: str, keyterms: list[str],
                         usage: dict, warnings: list[str]) -> list[dict]:
    # Concurrency is bounded by the provider's Gnani gate (GNANI_MAX_CONCURRENCY).
    return list(await asyncio.gather(*(transcribe_clip(stt, c, lang, keyterms, usage, warnings) for c in clips)))
