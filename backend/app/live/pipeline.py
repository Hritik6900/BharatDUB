"""Live pipeline: ingest PCM -> StreamingSTT -> Assembler -> per-language workers (translate -> TTS) -> Bus."""
import asyncio
import base64
import logging
import tempfile
import unicodedata
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np

from app.config import DEFAULT_GLOSSARY, VOICE_BY_LANG, get_settings
from app.db import get_store
from app.live.assembler import STT_SILENCE_MS, Assembler, Chunk, Phraser
from app.live.bus import ALL
from app.live.session import LiveSession
from app.providers import get_gpu_voice, get_llm, get_stt, get_tts
from app.providers.base import ProviderError, VoiceSpec
from app.shared import audio_utils as au
from app.shared.metrics import percentile

log = logging.getLogger("live")
TRANSLATE_TIMEOUT_S = 8.0
TTS_TIMEOUT_S = 20.0
ENROL_SPEECH_S = 12.0   # speech collected from the stream before the voice is copied (clone endpoint: 5-30 s)
ENROL_MIN_RMS = 300     # PCM16 units; frames quieter than this are pauses, not voice
LIVE_FRAME_BYTES = 9600  # audio message size on the watch socket: 0.2 s at 24 kHz
PLAYER_JITTER_MS = 300   # the web player starts an idle queue this long after the first audio arrives
GPU_REF_MIN_MS, GPU_REF_MS = 3500, 7000  # the voice sample for the GPU engine: the last 7 s before a pause (at least 3.5 s)
GPU_RETRY_MS = 8000        # the engine is tried again this long after it stopped answering
GPU_VOICE_LEAD_MS = 2200  # a GPU line takes about this long to make and arrive
SYNC_ARRIVE_MS = 100     # sync mode: audio that arrives after its moment starts this soon
MAX_QUEUED_AUDIO = 400  # ~13 s of 1024-byte frames; beyond that we drop (the streamer's network is ahead)


def _rms(pcm: bytes) -> float:
    x = np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype="<i2").astype(np.float64)
    return float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0


# One plain sentence per language, spoken in a freshly copied voice and heard back by Prisma, to judge the sample.
GPU_CHECK_LINES = {
    "hi-IN": "आज मौसम बहुत अच्छा है और हम सब यहाँ बहुत खुश हैं",
    "ta-IN": "இன்று வானிலை மிகவும் நன்றாக இருக்கிறது, நாங்கள் எல்லோரும் மகிழ்ச்சியாக இருக்கிறோம்",
    "te-IN": "ఈ రోజు వాతావరణం చాలా బాగుంది, మేమందరం చాలా సంతోషంగా ఉన్నాము",
    "bn-IN": "আজ আবহাওয়া খুব ভালো, আমরা সবাই এখানে খুব খুশি",
    "kn-IN": "ಇಂದು ಹವಾಮಾನ ತುಂಬಾ ಚೆನ್ನಾಗಿದೆ, ನಾವೆಲ್ಲರೂ ತುಂಬಾ ಸಂತೋಷವಾಗಿದ್ದೇವೆ",
    "ml-IN": "ഇന്ന് കാലാവസ്ഥ വളരെ നല്ലതാണ്, ഞങ്ങൾ എല്ലാവരും വളരെ സന്തോഷത്തിലാണ്",
    "mr-IN": "आज हवामान खूप छान आहे आणि आम्ही सगळे खूप आनंदी आहोत",
    "gu-IN": "આજે હવામાન ખૂબ સરસ છે અને અમે બધા ખૂબ ખુશ છીએ",
    "pa-IN": "ਅੱਜ ਮੌਸਮ ਬਹੁਤ ਵਧੀਆ ਹੈ ਅਤੇ ਅਸੀਂ ਸਾਰੇ ਬਹੁਤ ਖੁਸ਼ ਹਾਂ",
}
GPU_MAX_CHECKS = 3         # voice samples tried in one session
GPU_GOOD_SCORE = 0.85      # a sample this good is kept; below it a later pause may give a better one
GPU_RECHECK_MS = 12000     # ... but not sooner than this after the last try


def _words(text: str) -> list[str]:
    kept = "".join(c if unicodedata.category(c)[0] in "LMN" else " " for c in text.lower())
    return kept.split()


def words_heard(said: str, heard: str) -> float:
    """Share of the words in `said` that turn up in `heard` (same word, or the same first four letters)."""
    want, got = _words(said), set(_words(heard))
    if not want:
        return 0.0
    return sum(1 for w in want if w in got or any(w[:4] == g[:4] for g in got)) / len(want)


async def score_voice(gpu: Any, stt: Any, voice_id: str, lang: str) -> float | None:
    """How well a copied voice speaks: one known sentence, heard back by Prisma (share of words, 0-1).
    The sample decides everything about a copied voice, and this is the only way to know if it made a usable
    one (measured 2026-11-14: between 47% and 86% of words heard back, depending on the sample alone).
    None = no verdict (a call failed)."""
    line = GPU_CHECK_LINES.get(lang)
    if not line:
        return None
    wav = Path(tempfile.gettempdir()) / f"bd_gpu_check_{voice_id}.wav"
    try:
        pcm, rate = await gpu.synth(voice_id, line, lang)
        audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        await asyncio.to_thread(au.write_wav, wav, audio, rate)
        heard = (await stt.transcribe(str(wav), lang)).text
        score = words_heard(line, heard)
        per_word = len(audio) / rate * 1000 / max(1, len(line.split()))
        if not 250 <= per_word <= 1100:   # rushed or dragging speech is a bad sample whatever was understood
            score = min(score, 0.3)
        return round(score, 2)
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001 - no verdict
        log.warning("voice check failed: %s", e)
        return None
    finally:
        wav.unlink(missing_ok=True)


def speech_cut(frames: list[bytes], want_ms: int = GPU_REF_MS, min_ms: int = GPU_REF_MIN_MS,
               frame_ms: int = 32, keep_pause_ms: int = 450, hang_ms: int = 200) -> bytes | None:
    """The most recent `want_ms` of speech in `frames`, with long silences shortened to `keep_pause_ms`.

    A speaker who talks in short lines ("Answer.", "B wala chalo") never gives 3.5 s in one go (measured
    2026-11-14: the voice was learned 30 s after the first word). Joined like this, a few short lines are enough.
    The engine copies the pace of the sample, so the speech itself must stay as it was: everything within
    `hang_ms` of a loud frame counts as speech (quiet consonants, breaths), and pauses up to `keep_pause_ms` are
    kept whole. (Cutting every pause to 160 ms made the copied voice rush: 8 words in 1.4 s, 47% of the words
    heard back instead of 80%.) Returns None when there is less than `min_ms` of speech.
    """
    loud = [_rms(f) >= ENROL_MIN_RMS for f in frames]
    hang = max(1, hang_ms // frame_ms)
    # A quiet microphone has few "loud" frames, and the cut then ran to 15.7 s to collect 7 s of them (found 20 Nov
    # 2026). The engine works on sample + new line together, so the whole cut is capped as well.
    longest = (want_ms + 2000) // frame_ms
    speech = [any(loud[max(0, i - hang): i + hang + 1]) for i in range(len(frames))]
    out: list[bytes] = []
    voiced = gap = 0
    for f, sp in zip(reversed(frames), reversed(speech)):
        if sp:
            out.append(f)
            voiced += frame_ms   # speech, quiet consonants and breaths included: only loud frames undercounts a soft voice
            gap = 0
        else:
            gap += frame_ms
            if gap <= keep_pause_ms:
                out.append(f)
        if voiced >= want_ms or len(out) >= longest:
            break
    return b"".join(reversed(out)) if voiced >= min_ms else None


class LivePipeline:
    def __init__(self, sess: LiveSession, stt: Any = None, llm: Any = None, tts: Any = None,
                 gpu: Any = None) -> None:
        self.sess = sess
        # Our GPU voice engine (off unless GPU_VOICE_URL is set): the copied voice for Indian languages.
        self.gpu = gpu if gpu is not None else get_gpu_voice()
        self.gpu_ready = False     # the engine has this session's voice
        self._gpu_busy = False
        self._gpu_tries = 0
        self._gpu_fail = 0
        self._gpu_sid: str | None = None   # the voice on the engine that is in use
        self._gpu_score: float | None = None  # how well it speaks (share of words heard back), if known
        self._gpu_checks = 0
        self._gpu_last_try = 0
        self._gpu_stored = False           # the voice came from the streamer's profile, not from this stream
        self.stored_voice_ms: int | None = None  # how long sending it to the engines took
        self._gpu_retry_at = 0     # after three failures in a row: session time at which the engine is tried again
        self._ring: deque[tuple[int, bytes]] = deque(maxlen=700)  # ~22 s of the stream's sound, with arrival time
        self._prev_start: int | None = None
        self.stt, self.llm, self.tts = stt or get_stt(), llm or get_llm(), tts or get_tts()
        self.s = get_settings()
        self.audio: asyncio.Queue[bytes | None] = asyncio.Queue()
        self.assembler = Assembler()
        self.phraser = Phraser(self.s.live_phrase_min_words, self.s.live_phrase_max_words)
        self._voice_turn = asyncio.Semaphore(max(1, self.s.gnani_max_concurrency))
        self._gpu_turn = asyncio.Semaphore(max(1, int(getattr(self.gpu, "capacity", 1))))
        self._src_ms_per_word = 350.0             # how fast the speaker talks (from finished lines)
        self._dub_ms_per_word: dict[str, float] = {}  # per language: how long the dubbing voice takes per word
        self._gpu_ms_per_byte: dict[str, float] = {}  # per language: speech the GPU voice makes per byte of text
        self._playhead: dict[str, int] = {}  # per language: session time at which a viewer's queued dub ends
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
        # Sync mode: (session ms, video time in s, playing) reported by the console, newest last.
        self._media: deque[tuple[int, float, bool]] = deque(maxlen=1200)
        self._sync_delay = 0
        self._late: dict[str, deque[int]] = {}  # per language: how long after its moment each phrase started
        self._late_recent: deque[int] = deque(maxlen=6)
        self._viewer_late: deque[int] = deque(maxlen=500)  # reported by viewers' players
        self._ticks = 0
        self._lag: dict[str, int] = {}     # per language: how far behind the dub was at the last phrase (sync mode)
        self._starts: dict[int, int] = {}  # seq -> when that phrase began (to know how long the one before may run)
        self.sync_grown: list[tuple[int, int]] = []  # (session ms, new delay) each time the delay grew

    # ---------- lifecycle ----------
    async def start(self) -> None:
        if self.running:
            return
        self.running = True
        terms = [t["term"] for t in await get_store().select("glossary_terms")]
        self.glossary = list(dict.fromkeys(DEFAULT_GLOSSARY + terms))
        self.voice = await self._clone_voice()
        await self._use_stored_voice()
        consent = self.sess.row.get("voice_from_stream") or {}
        gpu_all = self.gpu.enabled and all(self.gpu.speaks(lg) for lg in self.sess.langs)
        if self.voice is None and consent.get("consent_at") and not gpu_all:
            self._enrol = []
        self.tasks = [asyncio.create_task(self._stt_loop()), asyncio.create_task(self._poll_loop())]
        if self.s.live_warmup and self.sess.langs:
            self.tasks.append(asyncio.create_task(self._warmup()))
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

    async def _warmup(self) -> None:
        """Open the connections to the translation model and the voice before the first phrase needs them
        (measured 2026-11-14: the first voice call of a session took 1.9 s, later ones 0.4 s)."""
        lang = self.sess.langs[0]

        async def voice() -> None:
            stock: VoiceSpec = {"kind": "stock", "voice": VOICE_BY_LANG.get(lang, VOICE_BY_LANG["hi-IN"])}
            async for _ in self.tts.synth_stream("ok", lang, stock, sample_rate=self.s.live_sample_rate):
                pass

        jobs = [self.llm.translate_chunk("नमस्ते", lang, [], [])]
        if not self._gpu_planned(lang):  # with the GPU voice coming, Gnani's one turn is kept free
            jobs.append(voice())
        for job in jobs:
            try:
                await asyncio.wait_for(job, TRANSLATE_TIMEOUT_S)
            except Exception:  # noqa: BLE001 - only a warm-up
                pass

    async def _use_stored_voice(self) -> None:
        """Streamer Mode: the voice the streamer recorded (with consent) goes to the GPU engines before the first
        word, so the first phrase is already in their voice. It is not replaced during the stream."""
        row = self.sess.row
        if not (row.get("streamer_id") and row.get("voice_mode") == "clone" and self.gpu.enabled):
            return
        p = await get_store().get("voice_profiles", row.get("voice_profile_id") or "")
        if not (p and p.get("consent_at") and p.get("ref_path") and p.get("ref_text") and not p.get("deleted_at")):
            return
        from app.shared.voices import voices_dir
        vid = f"voice-{p['id']}"
        t0 = self.sess.now_ms()
        try:
            await self.gpu.set_ref(vid, str(voices_dir() / p["ref_path"]), p["ref_text"], consent_at=p["consent_at"])
        except Exception as e:  # noqa: BLE001 - fail soft: the Gnani copy of the same voice, or stock
            log.warning("live stored voice: the engines did not take it (%s)", e)
            return
        self._gpu_sid, self._gpu_score, self._gpu_stored = vid, p.get("ref_score"), True
        self.gpu_ready = True
        self.voice_ready_ms = self.sess.now_ms()
        self.stored_voice_ms = self.sess.now_ms() - t0
        self.sess.bus.broadcast({"type": "voice", "cloned": True, "engine": "gpu", "t_ms": self.voice_ready_ms})

    def feed(self, pcm: bytes) -> None:
        if self.running and self.audio.qsize() < MAX_QUEUED_AUDIO:
            self.audio.put_nowait(pcm)
        if self._gpu_wanted():
            self._ring.append((self.sess.now_ms(), pcm))
        if self._enrol is not None and self._speaking and self.running:
            self._collect(pcm)

    # ---------- sync with the video ----------
    def set_media(self, media_s: float, playing: bool) -> None:
        """The console reports the current time of the video whose sound it is feeding.

        From then on a phrase is dubbed for the video moment it was spoken at, and viewers hold their own player
        `delay_ms` behind the console's, which gives translation and voice that long to be ready.
        """
        if not self.s.live_sync or not self.running or media_s < 0:
            return
        now = self.sess.now_ms()
        self._media.append((now, media_s, playing))
        if not self._sync_delay:
            # A copied voice from Gnani needs the longer start; our GPU engine is as quick as a stock voice.
            cloned = (self.voice is not None or self._enrol is not None) and not self.gpu.enabled
            self._sync_delay = self.s.live_sync_delay_clone_ms if cloned else self.s.live_sync_delay_ms
        self.sess.bus.broadcast({"type": "sync", "t_ms": now, "media_s": round(media_s, 3), "playing": playing,
                                 "delay_ms": self._sync_delay})

    def _note_late(self, late_ms: int) -> None:
        """Hold viewers back by what the dub really needs: when phrases keep starting after their moment, the
        delay grows by about that much (their video waits that long, once) instead of the dub staying behind."""
        self._late_recent.append(late_ms)
        late = sorted(v for v in self._late_recent if v > 400)
        if self.offset_delay():   # the offset is YouTube's delay, not ours to change
            return
        if not self.s.live_sync_adapt or len(late) < 3 or self._sync_delay >= self.s.live_sync_delay_max_ms:
            return
        step = min(3000, (late[len(late) // 2] // 500 + 1) * 500)
        self._sync_delay = min(self.s.live_sync_delay_max_ms, self._sync_delay + step)
        self._late_recent.clear()
        self.sync_grown.append((self.sess.now_ms(), self._sync_delay))

    # ---------- a streamer's own mic: the dub waits for YouTube ----------
    def offset_delay(self) -> int:
        """Streamer Mode with a mic: speech arrives here in real time, YouTube shows it `offset_ms` later, so every
        phrase is due that long after it was spoken. 0 = not that kind of session."""
        row = self.sess.row
        return int(row.get("offset_ms") or 0) if row.get("streamer_id") and not self._media else 0

    def viewer_played(self, lang: str, late_ms: int) -> None:
        """What a viewer's player measured: how long after its moment a phrase really started (0 = on it)."""
        if 0 <= late_ms < 120000:
            self._viewer_late.append(late_ms)

    def sync_delay(self) -> int:
        """The delay viewers hold their video at, or 0 when the console is not reporting video time (any more)."""
        if not self._media or self.sess.now_ms() - self._media[-1][0] > 5000:
            return self.offset_delay()
        return self._sync_delay

    def _media_at(self, t_ms: int) -> float:
        """Video time at session time `t_ms`, from the nearest report at or before it."""
        best = self._media[0]
        for p in reversed(self._media):
            if p[0] <= t_ms:
                best = p
                break
        t, media_s, playing = best
        return round(max(0.0, media_s + ((t_ms - t) / 1000 if playing else 0.0)), 3)

    def _media_tag(self, t_ms: int) -> dict[str, float]:
        # Only while the console is reporting a video's time (a streamer's mic session has a delay but no video time).
        fresh = bool(self._media) and self.sess.now_ms() - self._media[-1][0] <= 5000
        return {"media_s": self._media_at(t_ms)} if fresh and self._sync_delay else {}

    def sync_stats(self) -> dict[str, Any]:
        late = [v for d in self._late.values() for v in d][-300:]
        seen = list(self._viewer_late)[-300:]
        viewers = {"viewer_n": len(seen), "viewer_on_time_pct": round(100 * sum(v <= 1000 for v in seen) / len(seen), 1),
                   "viewer_late_p95_ms": int(percentile(seen, 95) or 0)} if seen else {}
        delay = self._sync_delay or self.offset_delay()
        if not delay or not late:
            return viewers
        return {**viewers, "sync_delay_ms": delay, "sync_n": len(late), "sync_grown": len(self.sync_grown),
                "sync_on_time_pct": round(100 * sum(v <= 250 for v in late) / len(late), 1),
                "sync_late_p95_ms": int(percentile(late, 95) or 0)}

    # ---------- copied voice on our GPU engine ----------
    def _gpu_wanted(self) -> bool:
        """Still looking for a voice sample for the GPU engine: only with the consent given for this stream."""
        consent = self.sess.row.get("voice_from_stream") or {}
        if not (self.running and self.gpu.enabled and self._gpu_tries < 8 and consent.get("consent_at")):
            return False
        if not self.gpu_ready:
            return True
        # It has a voice. A sample that did not score well may be replaced by a better one from a later pause.
        return (self._gpu_checks < GPU_MAX_CHECKS and (self._gpu_score or 0.0) < GPU_GOOD_SCORE
                and self.sess.now_ms() - self._gpu_last_try >= GPU_RECHECK_MS)

    def _gpu_planned(self, lang: str) -> bool:
        """This language is, or is about to be, spoken by the GPU engine (so its text is written for it)."""
        consent = self.sess.row.get("voice_from_stream") or {}
        return bool(self.gpu.enabled and (consent.get("consent_at") or self._gpu_stored) and self.gpu.speaks(lang)
                    and self._gpu_up() and (self.gpu_ready or self._gpu_tries < 8))

    def _gpu_up(self) -> bool:
        """The engine is answering, or it is time to try it again (the tunnel reconnects by itself)."""
        return self._gpu_fail < 3 or self.sess.now_ms() >= self._gpu_retry_at

    def _gpu_speaks(self, lang: str) -> bool:
        return self.gpu_ready and self._gpu_up() and self.gpu.speaks(lang)

    def _maybe_gpu_ref(self, text: str, now: int) -> None:
        """At a pause, the last few seconds of the stream become the voice sample for the engine, if they are
        mostly speech. Prisma then transcribes that very cut, so the sample and its words always match."""
        if self._gpu_busy or not self._gpu_wanted():
            return
        t1 = self._t_end if self._t_end is not None else now - STT_SILENCE_MS
        pcm = speech_cut([p for t, p in self._ring if t <= t1 + 350])
        if pcm is None:
            return
        self._gpu_busy = True
        self._gpu_tries += 1
        self.tasks.append(asyncio.create_task(self._gpu_enrol(pcm, text.strip())))

    async def _gpu_enrol(self, pcm: bytes, text: str) -> None:
        consent = self.sess.row.get("voice_from_stream") or {}
        wav = Path(tempfile.gettempdir()) / f"bd_gpu_ref_{self.sess.id}.wav"
        try:
            audio = np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0
            audio = np.concatenate([audio, np.zeros(4000, dtype=np.float32)])  # a clean stop: 0.25 s of silence
            await asyncio.to_thread(au.write_wav, wav, audio, 16000)
            # The engine copies pace and words from the sample, so its text must be exactly what is in this cut
            # (measured: a text longer than the audio made every phrase twice too fast). Prisma hears the cut itself.
            try:
                heard = (await self.stt.transcribe(str(wav), self.sess.row.get("src_lang") or "hi-IN")).text.strip()
            except Exception as e:  # noqa: BLE001 - mock STT or a failed call: keep the live transcript
                log.warning("live gpu voice sample: could not re-transcribe (%s)", e)
                heard = ""
            if len(heard.split()) >= 4:
                text = heard
            if len(text.split()) < 4:
                return  # nothing usable was said in this cut; the next pause tries again
            cand = f"{self.sess.id}-v{self._gpu_tries}"   # each sample is its own voice on the engine
            await self.gpu.set_ref(cand, str(wav), text, consent_at=consent.get("consent_at"))
            first = not self.gpu_ready
            if first:  # speak in it at once; whether it is a good one is found out while it is already in use
                self._gpu_sid = cand
                self.gpu_ready = True
                self.voice_ready_ms = self.voice_ready_ms or self.sess.now_ms()
                self.sess.bus.broadcast({"type": "voice", "cloned": True, "engine": "gpu", "t_ms": self.sess.now_ms()})
                self.sess.bus.broadcast({"type": "session", **self.sess.public()})
            score = await self._gpu_check(cand)
            self._gpu_checks += 1
            self._gpu_last_try = self.sess.now_ms()
            if first:
                self._gpu_score = score
            elif score is not None and score > (self._gpu_score or 0.0) + 0.08:
                self._gpu_sid, self._gpu_score = cand, score   # a clearly better sample: use it from now on
            log.info("live gpu voice sample %d: %.1f s, %d words, score %s, in use: %s", self._gpu_tries,
                     len(audio) / 16000, len(text.split()), score, self._gpu_sid == cand)
            self.sess.bus.broadcast({"type": "session", **self.sess.public()})
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - fail soft: the Gnani voices carry on
            log.warning("live gpu voice sample failed: %s", e)
        finally:
            self._gpu_busy = False
            wav.unlink(missing_ok=True)

    async def _gpu_check(self, cand: str) -> float | None:
        lang = next((lg for lg in self.sess.langs if self.gpu.speaks(lg) and lg in GPU_CHECK_LINES), None)
        return await score_voice(self.gpu, self.stt, cand, lang) if lang else None

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
                # A PC clock that is hours off makes every TLS certificate look "not yet valid" or "expired".
                why = ("this PC's date, time or time zone is wrong, so the secure connection is refused. Sync the clock "
                       "(Windows: Settings, Time & language, Sync now)." if "CERTIFICATE_VERIFY_FAILED" in str(e)
                       and ("not yet valid" in str(e) or "expired" in str(e)) else str(e)[:160])
                self.sess.bus.publish(ALL, {"type": "error", "message": f"Speech recognition: {why}"})
                await asyncio.sleep(1.0)
            else:
                if self.running:  # server closed the stream (session cap): reconnect
                    await asyncio.sleep(0.2)

    def _on_stt(self, ev: Any) -> None:
        now = self.sess.now_ms()
        if ev.kind == "final" and ev.text:
            self._maybe_gpu_ref(ev.text, now)
            n = len(ev.text.split())
            if n >= 3 and ev.audio_duration_ms:
                pace = min(700.0, max(150.0, ev.audio_duration_ms / n))
                self._src_ms_per_word = 0.8 * self._src_ms_per_word + 0.2 * pace
        elif ev.kind == "processing":
            self._maybe_gpu_ref("", now)
        if ev.kind == "connected":
            self._stt_t0 = now
            self.phraser.reset()
        elif ev.kind == "speech_start":
            self._prev_start, self._t_start = self._t_start, now
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
                t_start = min(t_end, now) - int(len(rest.split()) * self._src_ms_per_word)
                self._dispatch(self.assembler.make(rest, t_start_ms=t_start, t_end_ms=t_end, t_final_ms=now))
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
            self._ticks += 1
            if self._ticks % 10 == 0:   # the session clock, so viewers can place `t_speech_ms` on their own
                self.sess.bus.broadcast({"type": "clock", "t_ms": self.sess.now_ms(), "offset_ms": self.offset_delay()})
            chunk = self.assembler.poll(self.sess.now_ms())
            if chunk:
                self._dispatch(chunk)

    # ---------- fan-out ----------
    def _dispatch(self, chunk: Chunk) -> None:
        ctx = list(self.context)
        self.context.append(chunk.text)
        self.sess.chunk_count += 1
        self._starts[chunk.seq] = chunk.t_speech_ms
        self._starts.pop(chunk.seq - 200, None)
        self._pending[chunk.seq] = {"left": len(self.sess.langs), "src_text": chunk.text,
                                    "t_speech_ms": chunk.t_speech_ms,
                                    "timings": {"t_speech_end": chunk.t_speech_end_ms,
                                                "t_stt_final": chunk.t_stt_final_ms}}
        self.sess.bus.publish("src", {"type": "caption", "seq": chunk.seq, "lang": "src", "text": chunk.text,
                                      "t_speech_ms": chunk.t_speech_ms, **self._media_tag(chunk.t_speech_ms)})
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
            # While this language's dub is behind, a condensed translation lets it catch up (an interpreter does
            # the same). Decided now, because translation starts before the phrase's turn to be spoken.
            behind = self._lag.get(lang, 0) if self.sync_delay() else self._playhead.get(lang, 0) - self.sess.now_ms()
            kw: dict[str, Any] = {"brief": True} if self.s.live_brief and behind > self.s.live_brief_after_ms else {}
            pace = self._dub_ms_per_word.get(lang)
            if self.s.live_length_budget and pace:
                # Words that fit the time the speaker took: a little over when in step (a small speed-up is fine),
                # less when behind, much less when far behind (better a short line than a skipped one).
                share = 1.15 if not kw else 0.9 if behind <= 2000 else 0.6
                n_src = len(chunk.text.split())
                fit_words = max(2, int(n_src * self._src_ms_per_word * share / pace))
                if fit_words < n_src * 1.5:  # otherwise the limit says nothing
                    kw["max_words"] = fit_words
                    if chunk.seq in self._pending:
                        self._pending[chunk.seq]["timings"][f"budget:{lang}"] = fit_words
            if self._gpu_planned(lang):
                kw["native"] = True  # the GPU voice reads only the language's own letters
            if kw.get("brief") and chunk.seq in self._pending:
                self._pending[chunk.seq]["timings"][f"brief:{lang}"] = 1
            text = await asyncio.wait_for(self.llm.translate_chunk(chunk.text, lang, self.glossary, ctx, **kw),
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
                           "t_speech_ms": chunk.t_speech_ms, "untranslated": untranslated,
                           **self._media_tag(chunk.t_speech_ms)})
        return text, untranslated

    async def _worker(self, lang: str) -> None:
        q = self.queues[lang]
        while True:
            item = await q.get()
            if item is None:
                return
            batch = [item]
            # The voice is one Gnani request at a time, shared by every language. Waiting for the turn here
            # (not inside the provider) means that whatever piled up meanwhile and is already translated is
            # spoken together: one call instead of several, so the queue drains.
            await asyncio.wait({item[1]})  # translated first, so the turn is never held while waiting on the LLM
            # The copied voice is about to be ready (the sample is taken at the first pause): while this phrase
            # still has time before it is due, wait for it instead of starting in a stock voice.
            if self._gpu_planned(lang) and not self.gpu_ready and self.sync_delay():
                due = item[0].t_speech_ms + self.sync_delay() - GPU_VOICE_LEAD_MS
                while self.running and not self.gpu_ready and self._gpu_wanted() and self.sess.now_ms() < due:
                    await asyncio.sleep(0.1)
            # Lines for our GPU engine do not wait behind Gnani's one-at-a-time turn.
            turn = self._gpu_turn if self._gpu_speaks(lang) else self._voice_turn
            await turn.acquire()
            while len(batch) < self.s.live_merge_max and not q.empty():
                nxt = q._queue[0]  # type: ignore[attr-defined] - peek; only this worker takes from the queue
                if nxt is None or not nxt[1].done():
                    break
                batch.append(q.get_nowait())
            try:
                spoken: list[tuple[Chunk, str]] = []
                for chunk, task in batch:
                    text, untranslated = await task
                    if untranslated:
                        self.sess.bus.publish(lang, {"type": "audio", "seq": chunk.seq, "lang": lang,
                                                     "sample_rate": self.s.live_sample_rate, "pcm_b64": "",
                                                     "last": True})
                    else:
                        spoken.append((chunk, text))
                if spoken:
                    await self._speak(lang, spoken[0][0], " ".join(t for _, t in spoken), False,
                                      also=[c for c, _ in spoken[1:]])
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - one bad chunk must not stop the stream
                log.warning("live %s chunk %s failed: %s", lang, batch[0][0].seq, e)
                for chunk, _ in batch:
                    self.sess.bus.publish(lang, {"type": "audio", "seq": chunk.seq, "lang": lang,
                                                 "sample_rate": self.s.live_sample_rate, "pcm_b64": "",
                                                 "last": True})
            finally:
                turn.release()
                for chunk, _ in batch:
                    await self._chunk_done(chunk.seq)

    async def _speak(self, lang: str, chunk: Chunk, text: str, untranslated: bool,
                     also: "list[Chunk] | None" = None) -> None:
        """Speak `text` for `chunk`. `also` are later chunks whose text is included (merged into this call):
        their audio travels under this chunk's seq and they get the same timing marks."""
        bus, sr = self.sess.bus, self.s.live_sample_rate
        timings = self._pending[chunk.seq]["timings"]
        rest = [(c, self._pending[c.seq]["timings"]) for c in (also or []) if c.seq in self._pending]

        def end_of_audio() -> None:
            for c in [chunk, *[c for c, _ in rest]]:
                bus.publish(lang, {"type": "audio", "seq": c.seq, "lang": lang, "sample_rate": sr,
                                   "pcm_b64": "", "last": True})

        if untranslated:
            end_of_audio()
            return
        # Decided when this chunk's turn to speak comes. `waiting` is how much dubbed audio a viewer of this
        # language still has to play (see _playhead): a phrase is heard only after everything before it.
        now = self.sess.now_ms()
        waiting = max(0, self._playhead.get(lang, 0) - now)
        lag_ms = now + waiting - chunk.t_speech_end_ms
        # Sync mode: a viewer's video shows this phrase being spoken at `target` (session clock); the dub is due then.
        delay = self.sync_delay()
        target = chunk.t_speech_ms + delay if delay else None
        tag = self._media_tag(chunk.t_speech_ms)
        spare = target - now - waiting if target is not None else 0   # time left before it is due
        # With one Gnani request at a time, every line spoken delays the next one. Audio nobody is tuned to,
        # or that would be heard too late to feel live, is not made; its caption has already gone out.
        unheard = self.s.live_tts_only_heard and not bus.listeners(lang)
        too_late = -spare > self.s.live_sync_late_skip_ms if target is not None else lag_ms > self.s.live_skip_after_ms
        if unheard or too_late:
            for t in [timings, *[t for _, t in rest]]:
                t[f"skipped:{lang}"] = "unheard" if unheard else "late"
            end_of_audio()
            return
        if target is not None:
            # The audio is not needed before its moment, nor before the viewer has played what is queued: if
            # that leaves time to make a cloned line, use the copied voice.
            room = max(target - now, waiting)
            voice = self._voice_for(lang, 0 if room >= self.s.live_sync_clone_spare_ms else 10**9)
        else:
            voice = self._voice_for(lang, lag_ms)
        timings[f"clone:{lang}"] = int(voice["kind"] == "clone")
        # In sync mode the phrase is due in the future, so holding it back to fit it costs nothing.
        fit = self.s.live_fit and (target is not None or waiting > self.s.live_fit_after_ms)
        sent = 0   # bytes published
        lead = True
        held = b""  # audio kept back: the tail (to cut the silence after the last word), or all of it when fitting
        carry = b""
        keep_tail = int(sr * 0.3) * 2

        def publish(pcm: bytes) -> None:
            nonlocal sent
            if not pcm:
                return
            if not sent:
                t_first = self.sess.now_ms()
                timings[f"t_first_audio:{lang}"] = t_first
                self.sess.record_latency(lang, t_first - chunk.t_speech_end_ms)
                for c, t in rest:
                    t[f"t_first_audio:{lang}"] = t_first
                    t[f"merged:{lang}"] = chunk.seq
                    self.sess.record_latency(lang, t_first - c.t_speech_end_ms)
            sent += len(pcm)
            for k in range(0, len(pcm), LIVE_FRAME_BYTES):
                bus.publish(lang, {"type": "audio", "seq": chunk.seq, "lang": lang, "sample_rate": sr,
                                   "pcm_b64": base64.b64encode(pcm[k:k + LIVE_FRAME_BYTES]).decode(), "last": False,
                                   "t_speech_ms": chunk.t_speech_ms, **tag})

        def want_tempo(dur_ms: float) -> float:
            """How much faster a line of `dur_ms` has to be said to be in time (1 = as it is)."""
            still = max(0, self._playhead.get(lang, 0) - self.sess.now_ms())  # the backlog now, not when we began
            if target is None:
                return min(self.s.live_fit_max_tempo, 1 + still / max(dur_ms, 500))
            # It will start at `begin`. If the next phrase is known, end before that one is due; in any case
            # make up for whatever it is already late by.
            begin = max(self.sess.now_ms() + still, target)
            tempo = 1 + (begin - target) / max(dur_ms, 500)
            nxt = self._starts.get((rest[-1][0] if rest else chunk).seq + 1)
            if nxt is not None:
                room = nxt + delay + self.s.live_sync_slack_ms - begin
                tempo = max(tempo, dur_ms / max(room, 1))
            return min(self.s.live_fit_max_tempo, tempo)

        spoke_at = 1.0  # the speed the GPU voice was asked to speak at

        async def stream() -> None:
            nonlocal lead, held, carry, spoke_at
            if self._gpu_speaks(lang):
                try:
                    # The engine can speak faster by itself, which sounds better than squeezing the audio afterwards.
                    # How long the line will be is guessed from the lines before it (ms of speech per byte of text).
                    size = max(1, len(text.encode("utf-8")))
                    per_byte = self._gpu_ms_per_byte.get(lang)
                    speed = self.s.gpu_voice_speed
                    # Off by default: measured 2026-11-14 on 14 Tamil lines, the engine at 1.3x kept 70% of the
                    # words (Prisma hearing them back), against 82% for normal speed squeezed afterwards.
                    if fit and per_byte and self.s.gpu_voice_native_speedup:
                        speed = max(speed, want_tempo(per_byte * size / speed) * speed)
                        speed = min(speed, self.s.live_fit_max_tempo)
                    pcm, rate = await self.gpu.synth(self._gpu_sid or self.sess.id, text, lang, speed=speed)
                    spoke_at = speed / self.s.gpu_voice_speed
                    now_per_byte = len(pcm) / 2 / rate * 1000 * speed / size
                    self._gpu_ms_per_byte[lang] = now_per_byte if not per_byte else 0.7 * per_byte + 0.3 * now_per_byte
                    if rate != sr:
                        x = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
                        n = int(len(x) * sr / rate)
                        pcm = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype("<i2").tobytes()
                    held = au.trim_pcm_silence(pcm, start=True, end=False) if self.s.live_trim_silence else pcm
                    timings[f"clone:{lang}"] = timings[f"gpu:{lang}"] = 1
                    self._gpu_fail = 0
                    return
                except Exception as e:  # noqa: BLE001 - fail soft: this line goes to the Gnani voice instead
                    self._gpu_fail += 1
                    self._gpu_retry_at = self.sess.now_ms() + GPU_RETRY_MS
                    log.warning("live gpu voice failed (%d): %s", self._gpu_fail, e)
            async for pcm in self.tts.synth_stream(text, lang, voice, sample_rate=sr, speed=self.s.live_tts_speed):
                pcm = carry + pcm
                cut = len(pcm) // 2 * 2
                pcm, carry = pcm[:cut], pcm[cut:]
                if lead and self.s.live_trim_silence:
                    pcm = au.trim_pcm_silence(pcm, start=True, end=False)
                    if not pcm:
                        continue
                lead = False
                held += pcm
                if not fit and len(held) > keep_tail:
                    publish(held[:-keep_tail])
                    held = held[-keep_tail:]

        try:
            await asyncio.wait_for(stream(), TTS_TIMEOUT_S)
        except (ProviderError, TimeoutError) as e:
            bus.publish(ALL, {"type": "error", "message": f"{lang} voice failed: {str(e)[:120]}"}, to_all=False)
        if self.s.live_trim_silence:
            held = au.trim_pcm_silence(held, start=False, end=True)
        # The pace of this voice in this language, for the next phrases' word limit.
        said = len(text.split())
        raw_ms = (sent + len(held)) / 2 / sr * 1000 * spoke_at
        if said >= 2 and raw_ms > 200:
            prev = self._dub_ms_per_word.get(lang)
            self._dub_ms_per_word[lang] = raw_ms / said if not prev else 0.7 * prev + 0.3 * raw_ms / said
        if fit and held:
            # The viewer is still playing earlier phrases, so holding this one back costs nothing; it is
            # shortened (tempo only, pitch kept) by as much as it takes to catch up, within a limit.
            # What the GPU voice already sped up by itself counts towards that limit.
            tempo = min(self.s.live_fit_max_tempo / spoke_at, want_tempo(len(held) / 2 / sr * 1000))
            if tempo > 1.03:
                try:
                    held = await asyncio.to_thread(au.tempo_pcm, held, sr, tempo)
                except (au.FFmpegError, OSError) as e:
                    log.warning("live tempo fit failed: %s", e)
                    tempo = 1.0
            if tempo * spoke_at > 1.03:
                timings[f"tempo:{lang}"] = round(tempo * spoke_at, 2)
        publish(held)
        if sent:
            # Same rule as the web player: back to back with what is queued, else a jitter buffer after arrival.
            start = max(self._playhead.get(lang, 0), timings[f"t_first_audio:{lang}"] + PLAYER_JITTER_MS)
            if target is not None:  # the player holds it until the video reaches the phrase
                start = max(self._playhead.get(lang, 0), timings[f"t_first_audio:{lang}"] + SYNC_ARRIVE_MS, target)
                timings[f"late:{lang}"] = self._lag[lang] = start - target
                self._late.setdefault(lang, deque(maxlen=500)).append(start - target)
                # Only lateness in making the audio grows the delay; audio queued behind a long phrase does not.
                self._note_late(timings[f"t_first_audio:{lang}"] + SYNC_ARRIVE_MS - target)
            self._playhead[lang] = start + int(sent / 2 / sr * 1000)
            for c, t in [(chunk, timings), *rest]:
                t[f"t_heard:{lang}"] = start
                t[f"clone:{lang}"] = timings[f"clone:{lang}"]
                self.sess.record_heard(lang, start - c.t_speech_end_ms)
        end_of_audio()
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
        heard = [v for d in self.sess.heard.values() for v in d][-300:]
        h50, h95 = percentile(heard, 50), percentile(heard, 95)
        return {"p50_ms": int(p50) if p50 is not None else None, "p95_ms": int(p95) if p95 is not None else None,
                "n": len(all_ms), "heard_p50_ms": int(h50) if h50 is not None else None,
                "heard_p95_ms": int(h95) if h95 is not None else None, **self.sync_stats()}
