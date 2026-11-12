"""Live pipeline: ingest PCM -> StreamingSTT -> Assembler -> per-language workers (translate -> TTS) -> Bus."""
import asyncio
import base64
import logging
from collections import deque
from typing import Any

from app.config import DEFAULT_GLOSSARY, VOICE_BY_LANG, get_settings
from app.db import get_store
from app.live.assembler import STT_SILENCE_MS, Assembler, Chunk
from app.live.bus import ALL
from app.live.session import LiveSession
from app.providers import get_llm, get_stt, get_tts
from app.providers.base import ProviderError, VoiceSpec
from app.shared.metrics import percentile

log = logging.getLogger("live")
TRANSLATE_TIMEOUT_S = 8.0
TTS_TIMEOUT_S = 20.0
MAX_QUEUED_AUDIO = 400  # ~13 s of 1024-byte frames; beyond that we drop (the streamer's network is ahead)


class LivePipeline:
    def __init__(self, sess: LiveSession, stt: Any = None, llm: Any = None, tts: Any = None) -> None:
        self.sess = sess
        self.stt, self.llm, self.tts = stt or get_stt(), llm or get_llm(), tts or get_tts()
        self.s = get_settings()
        self.audio: asyncio.Queue[bytes | None] = asyncio.Queue()
        self.assembler = Assembler()
        self.context: deque[str] = deque(maxlen=3)
        self.queues: dict[str, asyncio.Queue[tuple[Chunk, list[str]] | None]] = {
            lg: asyncio.Queue() for lg in sess.langs}
        self.tasks: list[asyncio.Task[Any]] = []
        self.running = False
        self._t_start: int | None = None
        self._t_end: int | None = None
        self._pending: dict[int, dict[str, Any]] = {}
        self.glossary: list[str] = list(DEFAULT_GLOSSARY)
        self.voice: VoiceSpec | None = None

    # ---------- lifecycle ----------
    async def start(self) -> None:
        if self.running:
            return
        self.running = True
        terms = [t["term"] for t in await get_store().select("glossary_terms")]
        self.glossary = list(dict.fromkeys(DEFAULT_GLOSSARY + terms))
        self.voice = await self._clone_voice()
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

    async def _clone_voice(self) -> VoiceSpec | None:
        pid = self.sess.row.get("voice_profile_id")
        if not pid:
            return None
        p = await get_store().get("voice_profiles", pid)
        if p and p.get("consent_at") and p.get("embedding") and not p.get("deleted_at"):
            return {"kind": "clone", "embedding": p["embedding"]}
        return None

    def _voice_for(self, lang: str) -> VoiceSpec:
        return self.voice or {"kind": "stock", "voice": VOICE_BY_LANG.get(lang, VOICE_BY_LANG["hi-IN"])}

    # ---------- STT ----------
    async def _frames(self):  # type: ignore[no-untyped-def]
        while True:
            pcm = await self.audio.get()
            if pcm is None:
                return
            yield pcm

    async def _stt_loop(self) -> None:
        headers = {"x-min-silence-ms": str(STT_SILENCE_MS), "x-max-speech-s": "6", "x-idle-timeout-sec": "300"}
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
        if ev.kind == "speech_start":
            self._t_start = now
            self.assembler.speech_started()
            self.sess.bus.publish(ALL, {"type": "vad", "speaking": True}, to_all=False)
        elif ev.kind == "processing":
            self._t_end = now - STT_SILENCE_MS
            self.sess.bus.publish(ALL, {"type": "vad", "speaking": False}, to_all=False)
        elif ev.kind == "final" and ev.text:
            t_end = self._t_end if self._t_end is not None else now - STT_SILENCE_MS
            t_start = self._t_start if self._t_start is not None else t_end - (ev.audio_duration_ms or 0)
            self._t_start = self._t_end = None
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
        for q in self.queues.values():
            q.put_nowait((chunk, ctx))

    async def _worker(self, lang: str) -> None:
        q = self.queues[lang]
        while True:
            item = await q.get()
            if item is None:
                return
            chunk, ctx = item
            try:
                await self._process(lang, chunk, ctx)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - one bad chunk must not stop the stream
                log.warning("live %s chunk %s failed: %s", lang, chunk.seq, e)
                self.sess.bus.publish(lang, {"type": "audio", "seq": chunk.seq, "lang": lang,
                                             "sample_rate": self.s.live_sample_rate, "pcm_b64": "", "last": True})
            finally:
                await self._chunk_done(chunk.seq)

    async def _process(self, lang: str, chunk: Chunk, ctx: list[str]) -> None:
        bus, sr = self.sess.bus, self.s.live_sample_rate
        timings = self._pending[chunk.seq]["timings"]
        try:
            text = await asyncio.wait_for(self.llm.translate_chunk(chunk.text, lang, self.glossary, ctx),
                                          TRANSLATE_TIMEOUT_S)
            untranslated = False
        except (ProviderError, TimeoutError) as e:
            text, untranslated = chunk.text, True
            bus.publish(ALL, {"type": "error", "message": f"{lang} translation failed: {str(e)[:120]}"},
                        to_all=False)
        t_tr = self.sess.now_ms()
        timings[f"t_translated:{lang}"] = t_tr
        bus.publish(lang, {"type": "caption", "seq": chunk.seq, "lang": lang, "text": text,
                           "t_speech_ms": chunk.t_speech_ms, "untranslated": untranslated})
        if untranslated:
            bus.publish(lang, {"type": "audio", "seq": chunk.seq, "lang": lang, "sample_rate": sr,
                               "pcm_b64": "", "last": True})
            return
        first, carry = True, b""

        async def stream() -> None:
            nonlocal first, carry
            async for pcm in self.tts.synth_stream(text, lang, self._voice_for(lang), sample_rate=sr):
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
