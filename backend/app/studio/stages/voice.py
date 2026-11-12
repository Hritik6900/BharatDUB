"""Stage 7: synthesize one line (stock Timbre voice or cloned voice), cached by text + voice + settings."""
import hashlib
from pathlib import Path

from app.config import VOICE_BY_LANG
from app.providers.base import TTS, ProviderError, VoiceSpec
from app.shared import audio_utils as au
from app.shared import cache


def stock_voice(lang: str) -> VoiceSpec:
    return {"kind": "stock", "voice": VOICE_BY_LANG.get(lang, VOICE_BY_LANG["hi-IN"])}


def voice_id(voice: VoiceSpec) -> str:
    if voice["kind"] == "stock":
        return f"stock:{voice['voice']}"
    return "clone:" + hashlib.sha256(voice["embedding"]["embedding"].encode()).hexdigest()[:16]


async def synth_line(tts: TTS, text: str, lang: str, voice: VoiceSpec, tts_model: str, sr: int,
                     usage: dict, warnings: list[str]) -> Path:
    """Return a cached WAV path. A failing clone falls back to the stock voice for this line."""
    key = au.cache_key(text, lang, voice_id(voice), tts_model, sr)
    hit = cache.get_file("voice", key, "wav")
    if hit:
        usage["tts_cache_hits"] = usage.get("tts_cache_hits", 0) + 1
        return hit
    try:
        audio = await tts.synth(text, lang, voice)
    except ProviderError as e:
        if voice["kind"] != "clone":
            raise
        warnings.append(f"Cloned voice failed for a {lang} line, used stock voice: {str(e)[:120]}")
        return await synth_line(tts, text, lang, stock_voice(lang), tts_model, sr, usage, warnings)
    usage["tts_calls"] = usage.get("tts_calls", 0) + 1
    usage["tts_chars"] = usage.get("tts_chars", 0) + len(text)
    return cache.put_file("voice", key, "wav", audio)
