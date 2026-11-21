"""Studio's voice in `AI_MODE=gpu`: the copied voice comes from our GPU engine (IndicF5) instead of the hosted clone.

The hosted clone works from an embedding; our engine works from a short sample and the words spoken in it. So
`clone_embedding` here cuts about 7 s of speech out of the recording, has it transcribed and returns a reference to
that cut in the shape of an embedding (`dtype: "gpu-ref"`), which the Studio pipeline stores and passes around
unchanged. Everything the engine cannot do goes to the hosted provider when one is configured (`backup`): stock
voices (the engine has none), English, embeddings made by the hosted clone, streaming for Live, and any failure.
"""
import asyncio
import hashlib
import io
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from app.config import Settings, get_settings
from app.providers.base import ProviderError, VoiceSpec
from app.providers.tts_gnani import ConsentRequired

GPU_REF = "gpu-ref"
FRAME = 1024   # bytes: 32 ms of 16 kHz PCM16


class GpuStudioTTS:
    def __init__(self, gpu: Any, stt: Any, settings: Settings | None = None, backup: Any = None) -> None:
        self.gpu, self.stt, self.backup = gpu, stt, backup
        self.s = settings or get_settings()
        self._sent: set[str] = set()   # voices the engines already hold
        self.last_latency_s: float | None = None

    def _need_backup(self, what: str) -> Any:
        if self.backup is None:
            raise ProviderError(f"gpu voice: {what} needs the hosted voice service, which is not configured")
        return self.backup

    async def clone_embedding(self, wav_path: str, *, consent_at: str | None) -> dict[str, Any]:
        if not consent_at:
            raise ConsentRequired("voice cloning requires recorded consent", status=403)
        from app.live.pipeline import speech_cut
        from app.shared import audio_utils as au
        from app.shared.voices import voices_dir
        if not self.gpu.enabled:
            return await self._need_backup("a copied voice").clone_embedding(wav_path, consent_at=consent_at)  # type: ignore[no-any-return]
        x = await asyncio.to_thread(au.load_mono, Path(wav_path), 16000)
        pcm = (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()
        frames = [pcm[i:i + FRAME] for i in range(0, len(pcm) - FRAME + 1, FRAME)]
        cut = speech_cut(frames)
        if cut is None:
            raise ProviderError("gpu voice: too little speech in the sample")
        name = "gpuref_" + hashlib.sha256(cut).hexdigest()[:20] + ".wav"
        ref = voices_dir() / name
        audio = np.concatenate([np.frombuffer(cut, dtype="<i2").astype(np.float32) / 32768.0,
                                np.zeros(4000, dtype=np.float32)])   # a clean stop
        await asyncio.to_thread(au.write_wav, ref, audio, 16000)
        text = (await self.stt.transcribe(str(ref), "hi-IN")).text.strip()
        if len(text.split()) < 4:
            raise ProviderError("gpu voice: the sample's words could not be heard")
        own = {"ref_path": name, "ref_text": text, "consent_at": consent_at}
        if self.backup is not None:
            # With the hosted service at hand the profile gets its embedding too, so English and Live's fallback
            # keep the copied voice. Its failure is not ours: the engine reference alone is enough.
            try:
                return {**(await self.backup.clone_embedding(wav_path, consent_at=consent_at)), **own}
            except ProviderError:
                pass
        return {"embedding": name, "shape": [], "dtype": GPU_REF, **own}

    native_speed = True   # Studio may ask for a line again at a higher engine speed when it does not fit its slot

    def engine_speaks(self, lang: str, voice: VoiceSpec) -> bool:
        return voice["kind"] == "clone" and bool(dict(voice["embedding"]).get("ref_path")) and self.gpu.speaks(lang)

    async def synth(self, text: str, lang: str, voice: VoiceSpec, speed: float = 1.0) -> bytes:
        """Full WAV bytes at `tts_sample_rate`, like the hosted provider. `speed` > 1 = faster speech."""
        emb: dict[str, Any] = dict(voice["embedding"]) if voice["kind"] == "clone" else {}
        if not emb.get("ref_path") or not self.gpu.speaks(lang):
            return await self._need_backup("a stock voice, English, or a hosted clone").synth(text, lang, voice)  # type: ignore[no-any-return]
        from app.shared.voices import voices_dir
        vid = "studio-" + str(emb["ref_path"]).removesuffix(".wav")
        try:
            if vid not in self._sent:
                await self.gpu.set_ref(vid, str(voices_dir() / emb["ref_path"]), emb["ref_text"],
                                       consent_at=emb.get("consent_at"))
                self._sent.add(vid)
            pcm, rate = await self.gpu.synth(vid, text, lang, speed=speed * self.s.gpu_voice_speed)
        except ConsentRequired:
            raise
        except Exception as e:  # noqa: BLE001 - the caller falls back to a stock voice for this line
            self._sent.discard(vid)
            raise ProviderError(f"gpu voice: {str(e)[:160]}") from e
        self.last_latency_s = self.gpu.last_latency_s
        x = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        sr = self.s.tts_sample_rate
        if rate != sr:
            x = np.interp(np.linspace(0, len(x) - 1, int(len(x) * sr / rate)), np.arange(len(x)), x).astype(np.float32)
        buf = io.BytesIO()
        sf.write(buf, x, sr, format="WAV", subtype="PCM_16")
        return buf.getvalue()

    async def synth_stream(self, text: str, lang: str, voice: VoiceSpec, *, sample_rate: int | None = None,
                           speed: float = 1.0) -> AsyncIterator[bytes]:
        """Live's stock voices: only the hosted provider has them."""
        async for chunk in self._need_backup("a stock voice").synth_stream(text, lang, voice, sample_rate=sample_rate,
                                                                          speed=speed):
            yield chunk
