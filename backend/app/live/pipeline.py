"""Live pipeline: ingest PCM -> StreamingSTT -> Assembler -> per-language workers (translate -> TTS) -> Bus."""
import asyncio
import base64
import logging
import tempfile
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np

from app.config import DEFAULT_GLOSSARY, VOICE_BY_LANG, get_settings
from app.db import get_store
from app.live.assembler import STT_SILENCE_MS, Assembler, Chunk, Phraser
from app.live.bus import ALL
from app.live.session import LiveSession
from app.providers import get_llm, get_stt, get_tts
from app.providers.base import ProviderError, VoiceSpec
from app.shared import audio_utils as au
from app.shared.metrics import percentile

log = logging.getLogger("live")
TRANSLATE_TIMEOUT_S = 8.0
TTS_TIMEOUT_S = 20.0
ENROL_SPEECH_S = 12.0   # speech collected from the stream before the voice is copied (clone endpoint: 5-30 s)
ENROL_MIN_RMS = 300     # PCM16 units; frames quieter than this are pauses, not voice
MAX_QUEUED_AUDIO = 400  # ~13 s of 1024-byte frames; beyond that we drop (the streamer's network is ahead)


class LivePipeline:
    def __init__(self, sess: LiveSession, stt: Any = None, llm: Any = None, tts: Any = None) -> None:
        self.sess = sess
        self.stt, self.llm, self.tts = stt or get_stt(), llm or get_llm(), tts or get_tts()
        self.s = get_settings()
        self.audio: asyncio.Queue[bytes | None] = asyncio.Queue()
        self.assembler = Assembler()
        self.phraser = Phraser(self.s.live_phrase_min_words, self.s.live_phrase_max_words)
        self._stt_t0: int | None = None   # session clock at the start of the current STT stream
        self.context: deque[str] = deque(maxlen=3)
        self.queues: dict[str, asyncio.Queue[tuple[Chunk, asyncio.Task[tuple[str, bool]]] | None]] = {
            lg: asyncio.Queue() for lg in sess.langs}
        self._last_caption: dict[str, asyncio.Task[tuple[str, bool]]] = {}
        self.tasks: list[asyncio.Task[Any]] = []
        self.running = False
        self._t_start: int | None = None
        self._t_end: int | None = None
        self._pending: dict[int, dict[str, Any]] = {}
        self.voice_ready_ms: int | None = None
        self._speaking = False
        self._enrol: list[bytes] | None = None   # speech frames being collected for voice-from-stream
        self._enrol_bytes = 0
        self.glossary: list[str] = list(DEFAULT_GLOSSARY)
        self.voice: VoiceSpec | None = None
        self.clone_langs = sess.langs[: self.s.live_clone_langs or self.s.gnani_max_concurrency]

    # ---------- lifecycle ----------
    async def start(self) -> None:
        if self.running:
            return
        self.running = True
        terms = [t["term"] for t in await get_store().select("glossary_terms")]
        self.glossary = list(dict.fromkeys(DEFAULT_GLOSSARY + terms))
        self.voice = await self._clone_voice()
        consent = self.sess.row.get("voice_from_stream") or {}
        if self.voice is None and consent.get("consent_at"):
            self._enrol = []
        self.tasks = [asyncio.create_task(self._stt_loop()), asyncio.create_task(self._poll_loop())]
        self.tasks += [asyncio.create_task(self._worker(lg)) for lg in self.sess.langs]

    async def stop(self) -> None:
        if not self.running:
            return
        self.running = False
        await self.audio.put(None)
        chunk = self.assembler.flush()
        if chunk:
            self._dispatch(chunk)
        for q in self.queues.values():
            await q.put(None)
        await asyncio.sleep(0)
        done, pending = await asyncio.wait(self.tasks, timeout=15)
        for t in pending:
            t.cancel()

    def feed(self, pcm: bytes) -> None:
        if self.running and self.audio.qsize() < MAX_QUEUED_AUDIO:
            self.audio.put_nowait(pcm)
        if self._enrol is not None and self._speaking and self.running:
            self._collect(pcm)

    # ---------- voice from the stream ----------
    def _collect(self, pcm: bytes) -> None:
        """Keep frames that hold speech; once there is enough, copy the voice in the background."""
        samples = np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype="<i2")
        if not len(samples) or float(np.sqrt(np.mean(samples.astype(np.float64) ** 2))) < ENROL_MIN_RMS:
            return
        assert self._enrol is not None
        self._enrol.append(pcm)
        self._enrol_bytes += len(pcm)
        if self._enrol_bytes >= ENROL_SPEECH_S * 16000 * 2:
            frames, self._enrol = self._enrol, None
            self.tasks.append(asyncio.create_task(self._enrol_voice(b"".join(frames))))

    async def _enrol_voice(self, pcm: bytes) -> None:
        """Clone from the collected speech, only with the consent recorded at session creation (golden rule 4).

        Until this finishes (and if it fails) the stream is dubbed in stock voices.
        """
        consent = self.sess.row.get("voice_from_stream") or {}
        if not consent.get("consent_at"):
            return
        bus = self.sess.bus
        wav = Path(tempfile.gettempdir()) / f"bd_live_voice_{self.sess.id}.wav"
        try:
            audio = np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0
            await asyncio.to_thread(au.write_wav, wav, audio, 16000)
            emb = await self.tts.clone_embedding(str(wav), consent_at=consent["consent_at"])
            store = get_store()
            profile = await store.insert("voice_profiles", {
                "display_name": f"Voice from live {consent['consent_at'][:16].replace('T', ' ')}"[:60],
                "embedding": emb, "consent_text": consent.get("consent_text", ""),
                "consent_at": consent["consent_at"]})
            self.sess.row["voice_profile_id"] = profile["id"]
            await store.update("live_sessions", self.sess.id, {"voice_profile_id": profile["id"]})
            self.voice = {"kind": "clone", "embedding": emb}
            self.voice_ready_ms = self.sess.now_ms()
            bus.broadcast({"type": "voice", "cloned": True, "t_ms": self.voice_ready_ms})
            bus.broadcast({"type": "session", **self.sess.public()})
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - fail soft: keep dubbing in stock voices
            log.warning("live voice-from-stream failed: %s", e)
            bus.publish(ALL, {"type": "error", "message": "Could not copy the voice from this stream; "
                                                          f"using stock voices ({str(e)[:120]})"}, to_all=False)
        finally:
            wav.unlink(missing_ok=True)

    async def _clone_voice(self) -> VoiceSpec | None:
        pid = self.sess.row.get("voice_profile_id")
        if not pid:
            return None
        p = await get_store().get("voice_profiles", pid)
        if p and p.get("consent_at") and p.get("embedding") and not p.get("deleted_at"):
            return {"kind": "clone", "embedding": p["embedding"]}
        return None

    def _voice_for(self, lang: str, lag_ms: int = 0) -> VoiceSpec:
        """The speaker's cloned voice, unless this chunk is already late: then the stock voice, to catch up.

        Measured 2026-11-13: a cloned line takes 2-4 s to make (stock: ~0.5 s to first audio) and the account runs
        one request at a time, so several languages in the cloned voice fall further behind with every chunk
        (3 languages: 37 s behind after 55 s). So only the first `live_clone_langs` languages get the cloned voice.
        """
        if self.voice and lang in self.clone_langs and lag_ms <= self.s.live_clone_max_lag_ms:
            return self.voice
        return {"kind": "stock", "voice": VOICE_BY_LANG.get(lang, VOICE_BY_LANG["hi-IN"])}

    # ---------- STT ----------
    async def _frames(self):  # type: ignore[no-untyped-def]
        while True:
            pcm = await self.audio.get()
            if pcm is None:
                return
            yield pcm

    async def _stt_loop(self) -> None:
        headers = {"x-min-silence-ms": str(STT_SILENCE_MS), "x-max-speech-s": "6", "x-idle-timeout-sec": "300",
                   "format": get_settings().stt_format}
        if self.s.live_partials:
            # Undocumented switch (found 2026-11-13): partial_transcript events with stable_text, plus speech_end.
            # Phrases are cut from the partials, so an utterance may run longer before Prisma forces a final.
            headers |= {"x-partials": "true", "x-partial-interval-ms": str(self.s.live_partial_interval_ms)}
        while self.running:
            try:
                async for ev in self.stt.stream(self._frames(), self.sess.row.get("src_lang") or "indic-auto",
                                                extra_headers=headers):
                    self._on_stt(ev)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - reconnect (15 min cap, network)
                log.warning("live stt error: %s", e)
                self.sess.bus.publish(ALL, {"type": "error", "message": f"Speech recognition: {str(e)[:160]}"})
                await asyncio.sleep(1.0)
            else:
                if self.running:  # server closed the stream (session cap): reconnect
                    await asyncio.sleep(0.2)

    def _on_stt(self, ev: Any) -> None:
        now = self.sess.now_ms()
        if ev.kind == "connected":
            self._stt_t0 = now
            self.phraser.reset()
        elif ev.kind == "speech_start":
            self._t_start = now
            self._speaking = True
            self.assembler.speech_started()
            self.sess.bus.publish(ALL, {"type": "vad", "speaking": True}, to_all=False)
        elif ev.kind == "processing":
            # `speech_end` gives the stream-clock time at which the pause was declared (speech end + min silence).
            # Audio is fed in real time, so stream clock + stream start = session clock. Without it: arrival time.
            if ev.t_ms is not None and self._stt_t0 is not None:
                self._t_end = min(now, self._stt_t0 + int(ev.t_ms)) - STT_SILENCE_MS
            else:
                self._t_end = now - STT_SILENCE_MS
            self._speaking = False
            self.sess.bus.publish(ALL, {"type": "vad", "speaking": False}, to_all=False)
        elif ev.kind == "partial":
            self.sess.bus.publish(ALL, {"type": "partial", "text": ev.text, "t_ms": now}, to_all=False)
            cut = self.phraser.partial(ev.utterance_id, ev.stable_text, ev.text, now)
            if cut:
                held = self.assembler.flush()  # an earlier unfinished line goes out first, in order
                if held:
                    self._dispatch(held)
                text, t_start, t_end = cut
                self._dispatch(self.assembler.make(text, t_start_ms=t_start, t_end_ms=t_end, t_final_ms=now))
        elif ev.kind == "final" and ev.text and self.phraser.covered(ev.utterance_id):
            # Phrases of this utterance are already being dubbed: only the tail is left.
            rest = self.phraser.final(ev.utterance_id, ev.text)
            t_end = self._t_end if self._t_end is not None else now - STT_SILENCE_MS
            self._t_start = self._t_end = None
            self._speaking = False
            self.sess.bus.publish(ALL, {"type": "vad", "speaking": False}, to_all=False)
            self.sess.bus.publish(ALL, {"type": "transcript", "text": ev.text, "t_ms": now}, to_all=False)
            if rest:
                self._dispatch(self.assembler.make(rest, t_start_ms=min(t_end, now), t_end_ms=t_end, t_final_ms=now))
        elif ev.kind == "final" and ev.text:
            self.phraser.final(ev.utterance_id, ev.text)  # no phrase went out: forget the utterance
            t_end = self._t_end if self._t_end is not None else now - STT_SILENCE_MS
            t_start = self._t_start if self._t_start is not None else t_end - (ev.audio_duration_ms or 0)
            self._t_start = self._t_end = None
            self._speaking = False
            # Observed 2026-11-13: the real API sends no `processing` event, so the final also ends the "speaking" state.
            self.sess.bus.publish(ALL, {"type": "vad", "speaking": False}, to_all=False)
            self.sess.bus.publish(ALL, {"type": "transcript", "text": ev.text, "t_ms": now}, to_all=False)
            chunk = self.assembler.add(ev.text, t_start_ms=t_start, t_end_ms=t_end, t_final_ms=now)
            if chunk:
                self._dispatch(chunk)
        elif ev.kind == "error":
            self.sess.bus.publish(ALL, {"type": "error", "message": ev.message[:200]}, to_all=False)

    async def _poll_loop(self) -> None:
        while self.running:
            await asyncio.sleep(0.1)
            chunk = self.assembler.poll(self.sess.now_ms())
            if chunk:
                self._dispatch(chunk)

    # ---------- fan-out ----------
    def _dispatch(self, chunk: Chunk) -> None:
        ctx = list(self.context)
        self.context.append(chunk.text)
        self.sess.chunk_count += 1
        self._pending[chunk.seq] = {"left": len(self.sess.langs), "src_text": chunk.text,
                                    "t_speech_ms": chunk.t_speech_ms,
                                    "timings": {"t_speech_end": chunk.t_speech_end_ms,
                                                "t_stt_final": chunk.t_stt_final_ms}}
        self.sess.bus.publish("src", {"type": "caption", "seq": chunk.seq, "lang": "src", "text": chunk.text,
                                      "t_speech_ms": chunk.t_speech_ms})
        for lang, q in self.queues.items():
            # Translation starts now for every language (the LLM is not rate-limited like Gnani); only the
            # speaking is queued. A slow voice therefore never holds back the next caption's translation.
            prev = self._last_caption.get(lang)
            task = asyncio.create_task(self._translate(lang, chunk, ctx, prev))
            self._last_caption[lang] = task
            q.put_nowait((chunk, task))

    async def _translate(self, lang: str, chunk: Chunk, ctx: list[str],
                         prev: "asyncio.Task[tuple[str, bool]] | None") -> tuple[str, bool]:
        """Translate one chunk and publish its caption (captions stay in order per language)."""
        bus = self.sess.bus
        try:
            text = await asyncio.wait_for(self.llm.translate_chunk(chunk.text, lang, self.glossary, ctx),
                                          TRANSLATE_TIMEOUT_S)
            untranslated = False
        except (ProviderError, TimeoutError) as e:
            text, untranslated = chunk.text, True
            bus.publish(ALL, {"type": "error", "message": f"{lang} translation failed: {str(e)[:120]}"},
                        to_all=False)
        timings = self._pending[chunk.seq]["timings"] if chunk.seq in self._pending else {}
        timings[f"t_translated:{lang}"] = self.sess.now_ms()
        if prev is not None and not prev.done():
            await asyncio.wait({prev})
        bus.publish(lang, {"type": "caption", "seq": chunk.seq, "lang": lang, "text": text,
                           "t_speech_ms": chunk.t_speech_ms, "untranslated": untranslated})
        return text, untranslated

    async def _worker(self, lang: str) -> None:
        q = self.queues[lang]
        while True:
            item = await q.get()
            if item is None:
                return
            chunk, task = item
            try:
                text, untranslated = await task
                await self._speak(lang, chunk, text, untranslated)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - one bad chunk must not stop the stream
                log.warning("live %s chunk %s failed: %s", lang, chunk.seq, e)
                self.sess.bus.publish(lang, {"type": "audio", "seq": chunk.seq, "lang": lang,
                                             "sample_rate": self.s.live_sample_rate, "pcm_b64": "", "last": True})
            finally:
                await self._chunk_done(chunk.seq)

    async def _speak(self, lang: str, chunk: Chunk, text: str, untranslated: bool) -> None:
        bus, sr = self.sess.bus, self.s.live_sample_rate
        timings = self._pending[chunk.seq]["timings"]
        if untranslated:
            bus.publish(lang, {"type": "audio", "seq": chunk.seq, "lang": lang, "sample_rate": sr,
                               "pcm_b64": "", "last": True})
            return
        # Decided when this chunk's turn to speak comes, so the lag includes any queue behind earlier chunks.
        lag_ms = self.sess.now_ms() - chunk.t_speech_end_ms
        # With one Gnani request at a time, every line spoken delays the next one. Audio nobody is tuned to,
        # or that is already too late to feel live, is not made; its caption has already gone out.
        unheard = self.s.live_tts_only_heard and not bus.listeners(lang)
        if unheard or lag_ms > self.s.live_skip_after_ms:
            timings[f"skipped:{lang}"] = "unheard" if unheard else "late"
            bus.publish(lang, {"type": "audio", "seq": chunk.seq, "lang": lang, "sample_rate": sr,
                               "pcm_b64": "", "last": True})
            return
        voice = self._voice_for(lang, lag_ms)
        timings[f"clone:{lang}"] = int(voice["kind"] == "clone")
        first, carry = True, b""

        async def stream() -> None:
            nonlocal first, carry
            async for pcm in self.tts.synth_stream(text, lang, voice, sample_rate=sr, speed=self.s.live_tts_speed):
                pcm = carry + pcm
                cut = len(pcm) // 2 * 2
                pcm, carry = pcm[:cut], pcm[cut:]
                if not pcm:
                    continue
                if first:
                    first = False
                    t_first = self.sess.now_ms()
                    timings[f"t_first_audio:{lang}"] = t_first
                    latency = t_first - chunk.t_speech_end_ms
                    self.sess.record_latency(lang, latency)
                bus.publish(lang, {"type": "audio", "seq": chunk.seq, "lang": lang, "sample_rate": sr,
                                   "pcm_b64": base64.b64encode(pcm).decode(), "last": False})

        try:
            await asyncio.wait_for(stream(), TTS_TIMEOUT_S)
        except (ProviderError, TimeoutError) as e:
            bus.publish(ALL, {"type": "error", "message": f"{lang} voice failed: {str(e)[:120]}"}, to_all=False)
        bus.publish(lang, {"type": "audio", "seq": chunk.seq, "lang": lang, "sample_rate": sr, "pcm_b64": "",
                           "last": True})
        timings[f"t_audio_done:{lang}"] = self.sess.now_ms()
        self.sess.bus.broadcast({"type": "stats", **self.stats()})

    async def _chunk_done(self, seq: int) -> None:
        p = self._pending.get(seq)
        if not p:
            return
        p["left"] -= 1
        if p["left"] > 0:
            return
        self._pending.pop(seq, None)
        try:
            await get_store().insert("live_chunks", {"session_id": self.sess.id, "seq": seq,
                                                     "t_speech_ms": p["t_speech_ms"], "src_text": p["src_text"],
                                                     "timings": p["timings"]})
        except Exception as e:  # noqa: BLE001
            log.warning("could not save live chunk: %s", e)

    def stats(self) -> dict[str, Any]:
        all_ms = [v for d in self.sess.latencies.values() for v in d]
        p50, p95 = percentile(all_ms[-300:], 50), percentile(all_ms[-300:], 95)
        return {"p50_ms": int(p50) if p50 is not None else None, "p95_ms": int(p95) if p95 is not None else None,
                "n": len(all_ms)}
