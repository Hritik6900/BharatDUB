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
from app.live.assembler import PACE_MS, STT_SILENCE_MS, Assembler, Chunk, Phraser
from app.live.bus import ALL
from app.live.session import LiveSession
from app.providers import get_gpu_voice, get_judge, get_llm, get_stt, get_tts
from app.providers.base import ProviderError, VoiceSpec
from app.providers.llm_openai import wrong_script
from app.shared import audio_utils as au
from app.shared.metrics import percentile
from app.v1 import apilog, breaker, dense, guards, hold, record, trace, voicechain, warm
from app.v1.degrade import RUNGS, Ladder
from app.v1 import mode as v1mode
from app.v1.meaning import MeaningCheck
from app.v1.phrase import ShortLineMerger

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
GUARD_REDO_TIMEOUT_S = 4.0   # script guard: the one new translation of a line in the wrong script
BUDGET_LEAD_MS = 1500    # v1.1 budget: from the start of a translation to its first audio, about (measured p50 1.3-1.6 s)
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
EN = "en-IN"
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


async def send_stored_voice(row: dict[str, Any], gpu: Any, stt: Any) -> tuple[str, Any] | None:
    """Streamer Mode: the voice the streamer recorded (with consent) goes to the GPU engines. (voice id on the
    engines, its stored score), or None when this session has no such voice. Raises when no engine took it."""
    if not (row.get("streamer_id") and row.get("voice_mode") == "clone" and gpu.enabled):
        return None
    p = await get_store().get("voice_profiles", row.get("voice_profile_id") or "")
    if not (p and p.get("consent_at") and p.get("ref_path") and p.get("ref_text") and not p.get("deleted_at")):
        return None
    from app.shared.voices import voices_dir
    from app.streamer.voice_ref import sample_text
    vid = f"voice-{p['id']}"
    path = voices_dir() / p["ref_path"]
    text = await sample_text(p, path, row.get("src_lang") or "hi-IN", stt=stt)
    await gpu.set_ref(vid, str(path), text, consent_at=p["consent_at"])
    return vid, p.get("ref_score")


class LivePipeline:
    def __init__(self, sess: LiveSession, stt: Any = None, llm: Any = None, tts: Any = None,
                 gpu: Any = None, judge: Any = None) -> None:
        self.sess = sess
        # Our GPU voice engine (off unless GPU_VOICE_URL is set): the copied voice for Indian languages.
        # Which engine this session asked for: None = the hosted services as before, "gpu" = our own machine.
        eng = sess.row.get("engine") or None
        self.engine = eng
        self.gpu = gpu if gpu is not None else (get_gpu_voice(eng) if eng else get_gpu_voice())
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
        self.stt = stt or (get_stt(eng) if eng else get_stt())
        self.llm = llm or (get_llm(eng) if eng else get_llm())
        self.tts = tts or (get_tts(eng) if eng else get_tts())
        self.s = get_settings()
        # What is in force for this session is asked once, here, of the one place that knows (app/v1/mode.py).
        on = lambda name: v1mode.on(name, self.s)   # noqa: E731
        self._trace = on("trace")           # extra timing marks and one trace record per phrase
        self._budget = on("live_budget")    # the translator gets the phrase's slot as a length (app/v1/dense.py)
        # Auto mode: the budget applies only while a language's dub is behind or speech is dense, its scale comes
        # from the controller, and the meaning check may loosen it. Manual mode: the budget, when on, is on for
        # every phrase, scaled in two steps by how far behind the dub is; there is no controller.
        self._auto = self._budget and on("auto_budget")
        self._fallback = on("voice_fallback")       # a refused line is spoken by another voice
        self._script_guard = on("script_guard")
        self._breaker = on("breaker")
        self._late_shorten, self._backcheck = on("live_late_shorten"), on("live_backcheck")
        self.audio: asyncio.Queue[bytes | None] = asyncio.Queue()
        self.assembler = Assembler()
        self.phraser = Phraser(self.s.live_phrase_min_words, self.s.live_phrase_max_words)
        # Dense speech (auto budget): a line of one or two words waits for the next line and goes out with it.
        self._merger: ShortLineMerger | None = ShortLineMerger(
            self.s.v1_dense_merge_under_words, self.s.v1_merge_wait_ms) if self._auto else None
        self._stages: Any = None   # the scorer for the live back-check, made when first needed
        # The ladder (copied voice, stock voice, captions only, original sound). None = off.
        self._ladder = Ladder(sess.now_ms, fails=self.s.v1_degrade_fails,
                              probe_ms=self.s.v1_degrade_probe_ms) if on("live_degrade") else None
        self._rung: tuple[int, str] | None = None
        self.rungs: list[dict[str, Any]] = []   # every change of rung: {t_ms, rung, why}
        self._stored_busy = False
        self._stored_try_at = 0
        # Dense speech (app/v1/dense.py). `_dense_log`: dur_ratio, backlog and the rest are noted per phrase.
        self._dense_log = bool(self._trace or self._budget)
        self._xp = dense.ExpansionModel.load() if self._budget else None
        self._ctl: dict[str, dense.RateController] = {}   # auto budget: one controller per language
        self._gates: dict[str, dense.AutoGate] = {}       # auto budget: does it apply to this language now
        self.auto_log: list[dict[str, Any]] = []          # every time a language's budget went on or off
        self._share = dense.SpeakingShare(self.s.v1_dense_window_ms, self.s.v1_dense_share, self.s.v1_dense_off_share) \
            if self._dense_log else None
        self._wps = dense.WordRate(self.s.v1_dense_window_ms, self.s.v1_auto_wps_on, self.s.v1_auto_wps_off) \
            if self._auto else None
        self._dense = False   # speech is dense now (only ever in auto mode)
        # The meaning check (app/v1/meaning.py): a sample of spoken lines judged after the fact, off the path of a
        # phrase. Its loss rate loosens a language's budget (`meaning_check`); its other answer is the Live
        # content-shift count (`shift_check`).
        self._meaning: MeaningCheck | None = None
        if on("meaning_check") or on("shift_check"):
            self._meaning = MeaningCheck(judge if judge is not None else llm if llm is not None else get_judge(eng),
                                         sess.id, sess.langs, self.s, now_ms=sess.now_ms, behind=self._is_behind)
        self._loosen = on("meaning_check")
        self._meaning_task: asyncio.Task[None] | None = None
        # Guards and lines no voice made (v1.2): counted here, marked per phrase, in the trace and the metrics.
        self.guard = {"script_checked": 0, "script_failed": 0, "script_regenerated": 0, "script_flagged": 0,
                      "src_checked": 0, "src_failed": 0}
        self.voice_events: list[dict[str, Any]] = []   # every line another voice spoke, or that no voice spoke
        self.unspoken = 0
        # One English voice for the whole session (app/v1/warm.py).
        self._en_single = on("en_single_voice")
        self._en_auto = on("en_auto")
        self._copy_coming = False                          # the hosted copy is being learned from the stream
        self._en_mode: str | None = None                   # "copy" | "stock" for English; None = not that session
        self.en_choice: dict[str, Any] = {}                # how it was chosen (once)
        self._en_decided = asyncio.Event()
        self._en_decided.set()                             # cleared only while the probe of auto mode runs
        self.en_retries = [0, 0]                           # lines asked a second time, and how many then came
        self._voice_turn = asyncio.Semaphore(max(1, self.s.gnani_max_concurrency))
        self._gpu_turn = asyncio.Semaphore(max(1, int(getattr(self.gpu, "capacity", 1))))
        self._src_ms_per_word = 350.0             # how fast the speaker talks (from finished lines)
        self._dub_ms_per_word: dict[str, float] = {}  # per language: how long the dubbing voice takes per word
        self._gpu_ms_per_byte: dict[str, float] = {}  # per language: speech the GPU voice makes per byte of text
        self._gpu_ms_per_word: dict[str, float] = {}  # per language: the copied voice's own pace (engine speed 1)
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
        self._late_recent: dict[Any, int] = {}  # the last six phrases: how late their audio arrived (worst language)
        self._late_n = 0
        self._viewer_late: deque[int] = deque(maxlen=500)  # reported by viewers' players
        self._ticks = 0
        self._lag: dict[str, int] = {}     # per language: how far behind the dub was at the last phrase (sync mode)
        self._starts: dict[int, int] = {}  # seq -> when that phrase began (to know how long the one before may run)
        self._last_end = 0                 # when the phrase before this one ended (no phrase begins before that)
        self.sync_grown: list[tuple[int, int]] = []  # (session ms, new delay) each time the delay grew
        # `LIVE_SYNC_EASE`: the hold comes back down, step by step, once phrases are in time again (app/v1/hold.py).
        # Made when the hold is first set (its normal value is known then); None = the hold only ever grows.
        self._ease: hold.Ease | None = None
        # v1.1 `V1_LIVE_RECORD` and the session's own ask (record=true): the dub is kept on disk for the pitch
        # renderer (app/v1/record.py). None = nothing is kept, as SPEC section 10 says.
        self._rec = record.Recorder(sess.id, sess.langs, self.s.live_sample_rate, engine=eng or "cloud",
                                    src_lang=str(sess.row.get("src_lang") or "")) \
            if record.wanted(sess.row, self.s) else None

    # ---------- lifecycle ----------
    async def start(self) -> None:
        if self.running:
            return
        self.running = True
        apilog.set_test("live", self.sess.id)   # the API call log files this session's calls together
        terms = [t["term"] for t in await get_store().select("glossary_terms")]
        self.glossary = list(dict.fromkeys(DEFAULT_GLOSSARY + terms + list(self.sess.row.get("glossary") or [])))
        if self._breaker:
            breaker.watch().start()   # the link-stall detector runs while a session is live
        self.voice = await self._clone_voice()
        if self._ladder is None:
            await self._use_stored_voice()
        else:   # a GPU machine that does not answer must not hold the start up; the voice is asked for again later
            self._stored_try_at = self.sess.now_ms()
            try:
                await asyncio.wait_for(self._use_stored_voice(), self.s.v1_degrade_voice_wait_s)
            except TimeoutError:
                log.warning("live stored voice: no answer in %.0f s, starting without it", self.s.v1_degrade_voice_wait_s)
            self._rung = self.rung()    # where the session begins; every change from here on is announced
            self.rungs.append({"t_ms": self.sess.now_ms(), "rung": RUNGS[self._rung[0]], "why": self._rung[1]})
        consent = self.sess.row.get("voice_from_stream") or {}
        gpu_all = self.gpu.enabled and all(self.gpu.speaks(lg) for lg in self.sess.langs)
        if self.voice is None and consent.get("consent_at") and not gpu_all:
            self._enrol = []
            self._copy_coming = True
        self._en_start()
        if self._rec is not None:
            self._rec.start()
            if self._trace:
                trace.event("live_record", session=self.sess.id, langs=len(self.sess.langs))
        self.tasks += [asyncio.create_task(self._stt_loop()), asyncio.create_task(self._poll_loop())]
        if self.s.live_warmup and self.sess.langs:
            self.tasks.append(asyncio.create_task(self._warmup()))
        if self._meaning is not None and self._meaning.usable:
            self._meaning_task = asyncio.create_task(self._meaning.run())   # runs until the session stops
        self.tasks += [asyncio.create_task(self._worker(lg)) for lg in self.sess.langs]

    async def stop(self) -> None:
        if not self.running:
            return
        self.running = False
        if self._breaker:
            breaker.watch().stop()
        await self.audio.put(None)
        chunk = self.assembler.flush()
        if chunk:
            self._dispatch(chunk)
        if self._merger is not None:
            held = self._merger.flush()
            if held:
                self._dispatch(held, True)
        for q in self.queues.values():
            await q.put(None)
        await asyncio.sleep(0)
        done, pending = await asyncio.wait(self.tasks, timeout=15)
        for t in pending:
            t.cancel()
        if self._meaning_task is not None:   # lines still waiting to be judged are left unjudged
            self._meaning_task.cancel()
        if self._rec is not None:
            self._rec.close()
        if self._trace:
            trace.event("live_session_end", session=self.sess.id, phrases=self.sess.chunk_count,
                        engine=self.sess.row.get("engine") or "cloud", hold_ms=self._sync_delay,
                        hold_grown=len(self.sync_grown),
                        hold_eased=len(self._ease.steps) if self._ease is not None else None,
                        merged=self._merger.merged if self._merger else None,
                        short_alone=self._merger.alone if self._merger else None,
                        mode="auto" if v1mode.is_auto(self.s) else "manual",
                        budget_switches=len(self.auto_log) if self._auto else None,
                        unspoken=self.unspoken if self._fallback else None,
                        voice_fallbacks=len(self.voice_events) - self.unspoken if self._fallback else None,
                        guard=dict(self.guard) if self._script_guard else None,
                        meaning=self._meaning.stats()["by_lang"] if self._meaning is not None else None,
                        en_voice=self._en_mode)

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

    # ---------- the one English voice ----------
    def _en_start(self) -> None:
        """English is spoken in one voice for the whole session, chosen here, once (app/v1/warm.py).

        Manual mode (`V1_EN_SINGLE_VOICE`, GPU-engine sessions): the setting `V1_EN_VOICE`. Auto mode (every
        session with English): a value pinned in the overrides file; else the stock voice when the session has no
        copied voice at its start; else a measurement: one probe line in the copy, timed against the time a line
        has (`_en_probe`). Later changes come only from the ladder, on failure, and are logged as such."""
        if not (self._en_single and EN in self.sess.langs and (self._en_auto or self.engine == "gpu")):
            return
        if not self._en_auto:
            self._en_set(warm.en_mode(self.s.v1_en_voice), f"setting V1_EN_VOICE={self.s.v1_en_voice}")
            return
        pinned = v1mode.pin("en_voice", self.s)
        if pinned:
            self._en_set(pinned, "pinned in overrides.yaml")
        elif self.voice is None:
            self._en_set("stock", "a copy that is still to be learned from the stream is not there for the first lines"
                         if self._copy_coming else "the session has no copied voice for English")
        else:
            self._en_decided.clear()
            self.tasks.append(asyncio.create_task(self._en_probe()))

    async def _en_probe(self) -> None:
        """Auto mode: can the copied voice arrive in time? One probe line is made in the hosted copy and timed
        (the copy is not streamed: a line is there when all of it is). The time a line has is the viewers' hold
        less what is gone before the voice is asked (`v1_en_pipeline_ms`: the phrase itself and its text)."""
        hold_ms = self.offset_delay() or (self.s.live_sync_delay_ms if self.gpu.enabled else self.s.live_sync_delay_clone_ms)
        available = hold_ms - self.s.v1_en_pipeline_ms
        took: int | None = None
        error = ""
        try:
            assert self.voice is not None
            t0 = self.sess.now_ms()

            async def line() -> int:
                n = 0
                async with self._voice_turn:   # the hosted account's one request; before the first phrase needs it
                    async for pcm in self.tts.synth_stream(warm.EN_PROBE_LINE, EN, self.voice,
                                                           sample_rate=self.s.live_sample_rate):
                        n += len(pcm)
                return n
            made = await asyncio.wait_for(line(), self.s.v1_en_probe_timeout_s)
            if made:
                took = self.sess.now_ms() - t0
            else:
                error = "the copy made no sound"
        except asyncio.CancelledError:
            self._en_set("stock", "the session ended during the probe")
            raise
        except Exception as e:  # noqa: BLE001 - no answer in time is the answer
            error = f"{type(e).__name__}: {str(e)[:100]}" if not isinstance(e, TimeoutError) \
                else f"no answer in {self.s.v1_en_probe_timeout_s:.0f} s"
        choice, why = warm.en_choice(took, available, error)
        self._en_set(choice, why, probe_ms=took, available_ms=available, hold_ms=hold_ms)

    def _en_set(self, choice: str, why: str, **measured: Any) -> None:
        if self.en_choice:     # chosen once
            return
        self._en_mode = choice
        self.en_choice = {"voice": choice, "why": why, "t_ms": self.sess.now_ms(), **measured}
        self._en_decided.set()
        self.sess.row["en_voice"] = dict(self.en_choice)
        log.info("live %s: English in the %s voice for this session (%s)", self.sess.id[:8], choice, why)
        if self._trace:
            trace.event("live_en_voice", session=self.sess.id, mode=choice, why=why, auto=self._en_auto,
                        copy_at_start=self.voice is not None, **measured)

        async def keep() -> None:
            try:
                await get_store().update("live_sessions", self.sess.id, {"en_voice": dict(self.en_choice)})
            except Exception as e:  # noqa: BLE001 - the choice stands; only its record is missing
                log.warning("could not store the English voice choice: %s", e)
        try:
            self.tasks.append(asyncio.create_task(keep()))
        except RuntimeError:   # no running loop (a test that builds a pipeline without one)
            pass

    def warm_stats(self) -> dict[str, Any]:
        """For the session's metrics: the English voice. Empty when the session has no such choice."""
        out: dict[str, Any] = {}
        if self._en_mode is not None:
            out["en_voice"] = self._en_mode
            out["en_voice_choice"] = dict(self.en_choice)
            out["en_lines_asked_again"], out["en_lines_then_spoken"] = self.en_retries
        return out

    async def _use_stored_voice(self) -> None:
        """Streamer Mode: the voice the streamer recorded (with consent) goes to the GPU engines before the first
        word, so the first phrase is already in their voice. It is not replaced during the stream."""
        t0 = self.sess.now_ms()
        got: tuple[str, Any] | None = None
        try:
            if got is None:
                got = await send_stored_voice(self.sess.row, self.gpu, self.stt)
        except Exception as e:  # noqa: BLE001 - fail soft: the Gnani copy of the same voice, or stock
            log.warning("live stored voice: the engines did not take it (%s)", e)
            return
        if got is None:
            return
        self._gpu_sid, self._gpu_score, self._gpu_stored = got[0], got[1], True
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
            if self.s.live_sync_ease:
                self._ease = hold.Ease(self._sync_delay, step_ms=self.s.live_sync_ease_step_ms,
                                       every_ms=self.s.live_sync_ease_every_ms, calm_ms=self.s.live_sync_ease_after_ms,
                                       spare_ms=self.s.live_sync_ease_spare_ms)
        self.sess.bus.broadcast({"type": "sync", "t_ms": now, "media_s": round(media_s, 3), "playing": playing,
                                 "delay_ms": self._sync_delay})

    def _note_late(self, late_ms: int, seq: int | None = None) -> None:
        """Hold viewers back by what the dub really needs: when phrases keep starting after their moment, the
        delay grows by about that much (their video waits that long, once) instead of the dub staying behind.
        A phrase spoken in several languages is one phrase: its worst lateness counts, once."""
        if seq is None:
            self._late_n += 1
        key = seq if seq is not None else ("n", self._late_n)
        self._late_recent[key] = max(self._late_recent.get(key, late_ms), late_ms)
        while len(self._late_recent) > 6:
            self._late_recent.pop(next(iter(self._late_recent)))
        late = sorted(v for v in self._late_recent.values() if v > 400)
        if self.offset_delay():   # the offset is YouTube's delay, not ours to change
            return
        now = self.sess.now_ms()
        if self._ease is not None:
            self._ease.note(late_ms, now, seq)
        if not self.s.live_sync_adapt or len(late) < 3 or self._sync_delay >= self.s.live_sync_delay_max_ms:
            self._ease_hold(now)
            return
        step = min(self.s.live_sync_grow_step_ms, (late[len(late) // 2] // 500 + 1) * 500)
        self._sync_delay = min(self.s.live_sync_delay_max_ms, self._sync_delay + step)
        self._late_recent.clear()
        self.sync_grown.append((now, self._sync_delay))
        if self._ease is not None:
            self._ease.trouble(now)

    def _ease_hold(self, now: int) -> None:
        """The way back: after the hold grew (a stall of the link, a slow spell) and phrases are in time again
        for a while, it goes down a small step at a time to the value the session began with, never under it and
        never while a phrase is late. Viewers get the new value with the next `sync` message."""
        if self._ease is None or not self._sync_delay:
            return
        new = self._ease.next(self._sync_delay, now)
        if new != self._sync_delay:
            self._sync_delay = new
            if self._trace:
                trace.event("live_hold_eased", session=self.sess.id, hold_ms=new, at_ms=now)

    # ---------- a streamer's own mic: the dub waits for YouTube ----------
    def offset_delay(self) -> int:
        """Streamer Mode with a mic: speech arrives here in real time, YouTube shows it `offset_ms` later, so every
        phrase is due that long after it was spoken. 0 = not that kind of session."""
        row = self.sess.row
        return int(row.get("offset_ms") or 0) if row.get("streamer_id") and not self._media else 0

    def viewer_played(self, lang: str, late_ms: int, seq: int | None = None) -> None:
        """What a viewer's player measured: how long after its moment a phrase really started (0 = on it)."""
        if 0 <= late_ms < 120000:
            self._viewer_late.append(late_ms)
            if self._trace and seq is not None:
                trace.live_played(self.sess.id, seq, lang, late_ms)

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
                **({"sync_eased": len(self._ease.steps)} if self._ease is not None and self._ease.steps else {}),
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
            await self.gpu.set_ref(cand, str(wav), text, consent_at=consent.get("consent_at"),
                                   steps=self.s.gpu_voice_steps_stream)
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
                self._gpu_ms_per_word.clear()   # another sample, another pace
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
            self._copy_coming = False
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
        if self._en_mode is not None and lang == EN:
            # One English voice: never chosen line by line. The copy, once the session has it and while it
            # answers (the ladder may step down to the stock voice and back); else the one stock voice.
            if self._en_mode == "copy" and self.voice is not None and self._en_copy_up():
                return self.voice
            return self._stock(lang)
        if self.voice and lang in self.clone_langs and lag_ms <= self.s.live_clone_max_lag_ms:
            return self.voice
        return self._stock(lang)

    def _en_copy_up(self) -> bool:
        """With the ladder: the hosted copy is asked while it answers, and now and then while it does not."""
        return self._ladder is None or not self._ladder.down("copied") or self._ladder.may_try("copied")

    def _stock(self, lang: str) -> VoiceSpec:
        return voicechain.stock(lang)

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
                if self._ladder is not None:
                    self._ladder.note("stt", False)
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
        if self._ladder is not None and ev.kind != "error":
            self._ladder.note("stt", True)
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
            cut = self.phraser.partial(ev.utterance_id, ev.stable_text, ev.text, now,
                                       t0=self._t_start if self.s.live_stamp_fix else None)
            if cut:
                held = self.assembler.flush()  # an earlier unfinished line goes out first, in order
                if held:
                    self._dispatch(held)
                text, t_start, t_end = cut
                self._dispatch(self.assembler.make(text, t_start_ms=t_start, t_end_ms=t_end, t_final_ms=now))
        elif ev.kind == "final" and ev.text and self.phraser.covered(ev.utterance_id):
            # Phrases of this utterance are already being dubbed: only the tail is left.
            heard = self.phraser.tail_start(ev.utterance_id) if self.s.live_stamp_fix else None
            own = self.phraser.start_of(ev.utterance_id) if self.s.live_stamp_fix else None
            rest = self.phraser.final(ev.utterance_id, ev.text)
            t_end = self._t_end if self._t_end is not None else now - STT_SILENCE_MS
            self._utterance_over(own, t_end)
            self._speaking = False
            self.sess.bus.publish(ALL, {"type": "vad", "speaking": False}, to_all=False)
            self.sess.bus.publish(ALL, {"type": "transcript", "text": ev.text, "t_ms": now}, to_all=False)
            if rest:
                # When its first word was heard in a partial; if none showed it, counted back at the speaker's pace.
                t_start = min(t_end, now) - int(len(rest.split()) * self._src_ms_per_word)
                if heard is not None:
                    t_start = min(heard, t_end)
                total = len(ev.text.split())
                if own is not None and total and t_end > own:
                    # Best: the tail's share of the whole line, from where the line began to where it ended.
                    per = (t_end - own) / total
                    if PACE_MS[0] <= per <= PACE_MS[1]:
                        t_start = int(own + max(0, total - len(rest.split())) * per)
                self._dispatch(self.assembler.make(rest, t_start_ms=t_start, t_end_ms=t_end, t_final_ms=now))
        elif ev.kind == "final" and ev.text:
            own = self.phraser.start_of(ev.utterance_id) if self.s.live_stamp_fix else None
            self.phraser.final(ev.utterance_id, ev.text)  # no phrase went out: forget the utterance
            t_end = self._t_end if self._t_end is not None else now - STT_SILENCE_MS
            t_start = self._t_start if self._t_start is not None else t_end - (ev.audio_duration_ms or 0)
            if self.s.live_stamp_fix:
                if own is not None:
                    t_start = own
                if t_start > t_end:   # that speech start is the next utterance's, which has already begun
                    t_start = t_end - (ev.audio_duration_ms or 0)
            self._utterance_over(own, t_end)
            self._speaking = False
            # Observed 2026-11-13: the real API sends no `processing` event, so the final also ends the "speaking" state.
            self.sess.bus.publish(ALL, {"type": "vad", "speaking": False}, to_all=False)
            self.sess.bus.publish(ALL, {"type": "transcript", "text": ev.text, "t_ms": now}, to_all=False)
            chunk = self.assembler.add(ev.text, t_start_ms=t_start, t_end_ms=t_end, t_final_ms=now)
            if chunk:
                self._dispatch(chunk)
        elif ev.kind == "error":
            self.sess.bus.publish(ALL, {"type": "error", "message": ev.message[:200]}, to_all=False)

    def _utterance_over(self, own: int | None, t_end: int) -> None:
        """Forget the finished utterance's times. The next utterance can begin before this one's final transcript
        arrives: then the speech start on record is the next one's, and it is kept."""
        nxt = self.s.live_stamp_fix and self._t_start is not None and (
            (own is not None and self._t_start != own) or self._t_start > t_end)
        if not nxt:
            self._t_start = None
        self._t_end = None

    async def _poll_loop(self) -> None:
        while self.running:
            await asyncio.sleep(0.1)
            self._ticks += 1
            if self._ticks % 10 == 0:   # the session clock, so viewers can place `t_speech_ms` on their own
                self.sess.bus.broadcast({"type": "clock", "t_ms": self.sess.now_ms(), "offset_ms": self.offset_delay(),
                                         **(self._rung_tick() if self._ladder is not None else {})})
            if self._ticks % 100 == 0 and self._meaning is not None and self._loosen:
                self._meaning.tick()
            chunk = self.assembler.poll(self.sess.now_ms())
            if chunk:
                self._dispatch(chunk)
            if self._merger is not None:
                alone = self._merger.poll(self.sess.now_ms())
                if alone:
                    self._dispatch(alone, True)

    # ---------- fan-out ----------
    def _dispatch(self, chunk: Chunk, merged: bool = False) -> None:
        if self._merger is not None and not merged and (self._dense or self._merger.held is not None):
            # Dense speech: a line of one or two words waits for the next line and goes out as part of it.
            for c in self._merger.push(chunk, self.sess.now_ms()):
                self._dispatch(c, True)
            return
        if self.s.live_stamp_fix:
            # Phrases are spoken one after another, but their times are estimates: a phrase stamped as starting
            # before the one before it ended would have its dub due while that dub is still playing.
            chunk.t_speech_end_ms = max(chunk.t_speech_end_ms, chunk.t_speech_ms)
            chunk.t_speech_ms = min(max(chunk.t_speech_ms, self._last_end), chunk.t_speech_end_ms)
            self._last_end = max(self._last_end, chunk.t_speech_end_ms)
        ctx = list(self.context)
        self.context.append(chunk.text)
        self.sess.chunk_count += 1
        self._starts[chunk.seq] = chunk.t_speech_ms
        self._starts.pop(chunk.seq - 200, None)
        self._pending[chunk.seq] = {"left": len(self.sess.langs), "src_text": chunk.text,
                                    "t_speech_ms": chunk.t_speech_ms,
                                    "timings": {"t_speech_end": chunk.t_speech_end_ms,
                                                "t_stt_final": chunk.t_stt_final_ms}}
        if self._share is not None:
            self._note_share(chunk)
        if self._script_guard:
            # The transcript against the script of the language the session says is spoken (a transcript cannot
            # be made again: a line that fails is marked and counted, and translated as it is).
            ok = guards.transcript_script_ok(chunk.text, self.sess.row.get("src_lang"))
            if ok is not None:
                self.guard["src_checked"] += 1
                if not ok:
                    self.guard["src_failed"] += 1
                    self._pending[chunk.seq]["timings"]["src_script"] = 0
                    log.warning("live %s: phrase %d's transcript is not in the script of %s", self.sess.id[:8],
                                chunk.seq, self.sess.row.get("src_lang"))
        self.sess.bus.publish("src", {"type": "caption", "seq": chunk.seq, "lang": "src", "text": chunk.text,
                                      "t_speech_ms": chunk.t_speech_ms, **self._media_tag(chunk.t_speech_ms)})
        for lang, q in self.queues.items():
            # Translation starts now for every language (the LLM is not rate-limited like Gnani); only the
            # speaking is queued. A slow voice therefore never holds back the next caption's translation.
            prev = self._last_caption.get(lang)
            task = asyncio.create_task(self._translate(lang, chunk, ctx, prev))
            self._last_caption[lang] = task
            q.put_nowait((chunk, task))

    def _pace_boost(self, lang: str) -> float:
        """How much faster the copied voice is asked to speak in this language so that it reaches
        `gpu_voice_pace_ms` a word (1 = as the sample speaks). It does not count towards the squeeze limit."""
        pace = self._gpu_ms_per_word.get(lang)
        if not (self.s.gpu_voice_pace_ms > 0 and pace):
            return 1.0
        want = float(self.s.gpu_voice_pace_ms)
        if self.engine == "gpu" and self.s.gpu_voice_pace_follow > 0:
            # GPU engine only: a fast speaker gets a faster dub, down to `gpu_voice_pace_floor_ms` a word.
            want = min(want, max(float(self.s.gpu_voice_pace_floor_ms), self._src_ms_per_word * self.s.gpu_voice_pace_follow))
        return min(max(1.0, self.s.gpu_voice_pace_max), max(1.0, pace / want))

    def _note_gpu_pace(self, lang: str, ms_at_own_pace: float, words: int) -> None:
        if words < 4 or ms_at_own_pace < 300:
            return
        prev = self._gpu_ms_per_word.get(lang)
        now = ms_at_own_pace / words
        self._gpu_ms_per_word[lang] = now if not prev else 0.7 * prev + 0.3 * now

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
            # Auto mode: the budget applies only while this language's dub is behind or speech is dense; outside
            # that the translator gets the full prompt: no word limit, no "be brief".
            full = self._auto and not self._budget_now(lang)
            plan = self._budget_plan(lang, chunk, behind) if self._budget and not full else None
            if self._auto and chunk.seq in self._pending:
                self._pending[chunk.seq]["timings"][f"auto:{lang}"] = int(plan is not None)
            if plan is not None:
                # The phrase's own slot as words and letters; the answer is checked below.
                kw = {"max_words": plan["max_words"], "max_chars": plan["max_chars"], "compact": True}
                if plan["scale"] < 0.8:
                    kw["brief"] = True
            elif full:
                kw = {}
            elif self.s.live_length_budget and pace:
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
            fell = getattr(self.llm, "fell_back", 0)
            if self._trace and chunk.seq in self._pending:
                self._pending[chunk.seq]["timings"][f"t_translate_start:{lang}"] = self.sess.now_ms()
            text = await asyncio.wait_for(self.llm.translate_chunk(chunk.text, lang, self.glossary, ctx, **kw),
                                          TRANSLATE_TIMEOUT_S)
            untranslated = False
            if self._trace and chunk.seq in self._pending and getattr(self.llm, "fell_back", 0) != fell:
                self._pending[chunk.seq]["timings"][f"llm_fb:{lang}"] = 1
            if plan is not None:
                text = await self._within_budget(lang, chunk, text, plan)
            if self._script_guard:
                text = await self._script_checked(lang, chunk, text, ctx, bool(kw.get("native")))
        except (ProviderError, TimeoutError) as e:
            text, untranslated = chunk.text, True
            bus.publish(ALL, {"type": "error", "message": f"{lang} translation failed: {str(e)[:120]}"},
                        to_all=False)
        if self._ladder is not None:
            self._ladder.note("translate", not untranslated)
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
            if lang == EN and not self._en_decided.is_set():
                # Auto mode: the English voice is being chosen (one probe line, at most `v1_en_probe_timeout_s`).
                # The first English lines wait for it, so that the session never changes voice.
                await self._en_decided.wait()
            if self._en_mode == "copy" and lang == EN and self.voice is None and self._copy_coming and self.sync_delay():
                # One English voice: the same for the hosted copy of English, which takes longer to make.
                due = item[0].t_speech_ms + self.sync_delay() - self.s.v1_en_copy_lead_ms
                while self.running and self.voice is None and self._copy_coming and self.sess.now_ms() < due:
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
                        self._mark_unspoken(lang, [chunk], "untranslated")
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
                self._mark_unspoken(lang, [c for c, _ in batch], f"error: {type(e).__name__}")
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
            if self._ladder is not None:
                timings[f"rung:{lang}"] = 3
            if self._rec is not None:
                self._rec.skip(lang, chunk.seq, "untranslated", t_speech_ms=chunk.t_speech_ms)
            end_of_audio()
            return
        if self._trace:
            timings[f"tts_chars:{lang}"] = len(text)
        gpu_spoke = False   # this line came from our voice engine
        tried: list[str] = []                    # the voices asked for this line, in order (app/v1/voicechain.py)
        failed: list[dict[str, str]] = []        # ... and what each one that made nothing answered

        def kind_of(v: VoiceSpec) -> str:
            return "copy" if v["kind"] == "clone" else "stock"

        def fail(kind: str, e: BaseException | str) -> None:
            failed.append({"voice": kind, "error": e if isinstance(e, str) else f"{type(e).__name__}: {str(e)[:120]}"})
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
        max_tempo = self.s.live_fit_max_tempo
        if self._dense_log:
            # How far the dub queue is behind the video when this phrase's turn comes: what is still to be played
            # beyond the phrase's own moment (sync mode), or simply what is still to be played.
            backlog = max(0, self._playhead.get(lang, 0) - target) if target is not None else waiting
            for t in [timings, *[t for _, t in rest]]:
                t[f"backlog:{lang}"] = backlog
            if self._auto:
                ctl = self._controller(lang)
                ctl.update(backlog / 1000, now / 1000)
                timings[f"ctl_i:{lang}"] = round(ctl.integral, 2)
                # For the gate, "behind" is also a phrase whose turn comes after its own moment (its sound is being
                # made late: a slow voice, a stall), not only sound queued behind sound. The controller keeps the
                # backlog alone, as it was measured.
                self._gate_update(lang, now, chunk.seq, backlog_ms=max(backlog, -spare) if target is not None else backlog)
                if self._dense:
                    max_tempo = max(max_tempo, self.s.v1_dense_max_tempo)
        # With one Gnani request at a time, every line spoken delays the next one. Audio nobody is tuned to,
        # or that would be heard too late to feel live, is not made; its caption has already gone out.
        unheard = self.s.live_tts_only_heard and not bus.listeners(lang)
        too_late = -spare > self.s.live_sync_late_skip_ms if target is not None else lag_ms > self.s.live_skip_after_ms
        if too_late and not unheard and self._late_shorten:
            # v1: a late line is said in a shorter version; it is skipped only when it is far too late.
            late_by = -spare if target is not None else lag_ms
            limit = self.s.live_sync_late_skip_ms if target is not None else self.s.live_skip_after_ms
            shorter = await self._shorter(lang, text, late_by, limit)
            if shorter:
                text, too_late = shorter, False
                timings[f"shortened:{lang}"] = 1
        if unheard or too_late:
            for t in [timings, *[t for _, t in rest]]:
                t[f"skipped:{lang}"] = "unheard" if unheard else "late"
            if too_late and not unheard and self._ease is not None:   # a phrase too late to be spoken: the hold stays
                self._ease.trouble(now)
            if self._rec is not None:
                self._rec.skip(lang, chunk.seq, "unheard" if unheard else "late", t_speech_ms=chunk.t_speech_ms,
                               also=[c.seq for c, _ in rest] or None, **tag)
            end_of_audio()
            return
        if self._ladder is not None and not self._voice_may_try(lang):
            # Captions only: no voice answers. One line now and then still tries; that is the way back.
            for t in [timings, *[t for _, t in rest]]:
                t[f"skipped:{lang}"], t[f"rung:{lang}"] = "degraded", 2
            if self._rec is not None:
                self._rec.skip(lang, chunk.seq, "degraded", t_speech_ms=chunk.t_speech_ms,
                               also=[c.seq for c, _ in rest] or None, **tag)
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
        kept: list[bytes] = []   # `V1_LIVE_RECORD`: what went out, for the recording
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
            if self._rec is not None:
                kept.append(pcm)
            for k in range(0, len(pcm), LIVE_FRAME_BYTES):
                bus.publish(lang, {"type": "audio", "seq": chunk.seq, "lang": lang, "sample_rate": sr,
                                   "pcm_b64": base64.b64encode(pcm[k:k + LIVE_FRAME_BYTES]).decode(), "last": False,
                                   "t_speech_ms": chunk.t_speech_ms, **tag})

        def want_tempo(dur_ms: float) -> float:
            """How much faster a line of `dur_ms` has to be said to be in time (1 = as it is)."""
            still = max(0, self._playhead.get(lang, 0) - self.sess.now_ms())  # the backlog now, not when we began
            if target is None:
                return min(max_tempo, 1 + still / max(dur_ms, 500))
            # It will start at `begin`. If the next phrase is known, end before that one is due; in any case
            # make up for whatever it is already late by.
            begin = max(self.sess.now_ms() + still, target)
            tempo = 1 + (begin - target) / max(dur_ms, 500)
            nxt = self._starts.get((rest[-1][0] if rest else chunk).seq + 1)
            if nxt is not None:
                room = nxt + delay + self.s.live_sync_slack_ms - begin
                tempo = max(tempo, dur_ms / max(room, 1))
            return min(max_tempo, tempo)

        spoke_at = 1.0  # the speed the GPU voice was asked to speak at

        async def hosted(voice: VoiceSpec) -> None:
            nonlocal lead, held, carry
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

        async def stream() -> None:
            nonlocal held, spoke_at, gpu_spoke, lead, carry
            if self._gpu_speaks(lang):
                tried.append("gpu")
                try:
                    # The engine can speak faster by itself, which sounds better than squeezing the audio afterwards.
                    # How long the line will be is guessed from the lines before it (ms of speech per byte of text).
                    size = max(1, len(text.encode("utf-8")))
                    per_byte = self._gpu_ms_per_byte.get(lang)
                    base = speed = self.s.gpu_voice_speed * self._pace_boost(lang)
                    # Off by default: measured 2026-11-14 on 14 Tamil lines, the engine at 1.3x kept 70% of the
                    # words (Prisma hearing them back), against 82% for normal speed squeezed afterwards.
                    if fit and per_byte and self.s.gpu_voice_native_speedup:
                        speed = max(speed, want_tempo(per_byte * size / speed) * speed)
                        speed = min(speed, self.s.live_fit_max_tempo)
                    pcm, rate = await self.gpu.synth(self._gpu_sid or self.sess.id, text, lang, speed=speed)
                    if self._backcheck:
                        pcm, rate = await self._checked(lang, text, pcm, rate, speed, target, timings)
                    spoke_at = speed / base
                    # The pace is taken from the speech alone: the silence around a short line would read as slow speech.
                    spoken = au.trim_pcm_silence(au.trim_pcm_silence(pcm, start=True, end=False), start=False, end=True)
                    self._note_gpu_pace(lang, len(spoken) / 2 / rate * 1000 * speed / self.s.gpu_voice_speed, len(text.split()))
                    if base > self.s.gpu_voice_speed * 1.03:
                        timings[f"pace:{lang}"] = round(base / self.s.gpu_voice_speed, 2)
                    now_per_byte = len(pcm) / 2 / rate * 1000 * speed / size
                    self._gpu_ms_per_byte[lang] = now_per_byte if not per_byte else 0.7 * per_byte + 0.3 * now_per_byte
                    if rate != sr:
                        x = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
                        n = int(len(x) * sr / rate)
                        pcm = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype("<i2").tobytes()
                    held = au.trim_pcm_silence(pcm, start=True, end=False) if self.s.live_trim_silence else pcm
                    timings[f"clone:{lang}"] = timings[f"gpu:{lang}"] = 1
                    if self._trace and getattr(self.gpu, "last_synth_ms", None):
                        timings[f"gpu_ms:{lang}"] = round(float(self.gpu.last_synth_ms))
                    self._gpu_fail = 0
                    gpu_spoke = True
                    if self._ladder is not None:
                        self._ladder.note("copied", True)
                    return
                except Exception as e:  # noqa: BLE001 - fail soft: this line goes to the Gnani voice instead
                    self._gpu_fail += 1
                    if self._ladder is not None:
                        self._ladder.note("copied", False)
                    self._gpu_retry_at = self.sess.now_ms() + GPU_RETRY_MS
                    log.warning("live gpu voice failed (%d): %s", self._gpu_fail, e)
                    fail("gpu", e)
                    if self._trace:
                        timings[f"tts_fb:{lang}"] = 1
            tried.append(kind_of(voice))
            again = (self._en_mode is not None and lang == EN) or (self._fallback and kind_of(voice) in voicechain.RETRY_SAME)
            if not again:
                await hosted(voice)
                return
            # A line the hosted voice refused before any sound (seen 25 Nov 2026: one stock line in three answered
            # "technical difficulties", HTTP 502, within 0.2 s) is asked once more in the same voice. The streamed
            # call has no retry of its own. (The one English voice: either voice. Auto mode: every stock line.)
            try:
                await hosted(voice)
            except ProviderError as e:
                if sent or held:
                    raise
                self.en_retries[0] += 1
                timings[f"tts_retry:{lang}"] = 1
                log.info("live %s: the hosted voice refused a line (%s), asked once more", lang, str(e)[:80])
                lead, carry = True, b""
                await asyncio.sleep(0.2)
                await hosted(voice)
                self.en_retries[1] += 1

        try:
            await asyncio.wait_for(stream(), TTS_TIMEOUT_S)
        except (ProviderError, TimeoutError) as e:
            fail(tried[-1] if tried else "stock", e)
            bus.publish(ALL, {"type": "error", "message": f"{lang} voice failed: {str(e)[:120]}"}, to_all=False)
        except Exception as e:  # noqa: BLE001 - e.g. the hosted voice's connection dropped mid-line
            if self._ladder is None:
                raise   # as before: the worker closes the phrase
            fail(tried[-1] if tried else "stock", e)
            log.warning("live %s voice failed: %s: %s", lang, type(e).__name__, str(e)[:120])
        if not gpu_spoke and not (sent or held) and not failed:
            fail(tried[-1] if tried else "stock", "made no sound")
        if self._ladder is not None:
            if not gpu_spoke:
                made = bool(sent or held)
                self._ladder.note("copied" if voice["kind"] == "clone" else "stock", made)
                if not made and voice["kind"] == "clone":
                    # The hosted copy of the voice did not answer: a stock voice says this line.
                    voice = self._stock(lang)
                    timings[f"clone:{lang}"] = 0
                    tried.append("stock")
                    lead, carry = True, b""
                    try:
                        await asyncio.wait_for(hosted(voice), TTS_TIMEOUT_S)
                    except Exception as e:  # noqa: BLE001 - no voice for this line; its caption is out
                        fail("stock", e)
                        bus.publish(ALL, {"type": "error", "message": f"{lang} voice failed: {str(e)[:120]}"}, to_all=False)
                    self._ladder.note("stock", bool(sent or held))
        if self._fallback and not gpu_spoke and not (sent or held):
            # Every voice that is left is asked, in the one order (app/v1/voicechain.py): a line is left without
            # sound only when none of them makes it.
            can = {"stock"}
            if self.gpu.enabled and self.gpu_ready and self.gpu.speaks(lang):
                can.add("gpu")
            if self.voice is not None:
                can.add("copy")
            alt = voicechain.stock_alt(lang)
            if alt is not None:
                can.add("stock_alt")
            for k in voicechain.rest(tried, can):
                tried.append(k)
                lead, carry, held = True, b"", b""
                try:
                    if k == "gpu":
                        pcm, rate = await asyncio.wait_for(
                            self.gpu.synth(self._gpu_sid or self.sess.id, text, lang,
                                           speed=self.s.gpu_voice_speed * self._pace_boost(lang)), voicechain.LATER_TIMEOUT_S)
                        if rate != sr:
                            x = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
                            n = int(len(x) * sr / rate)
                            pcm = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype("<i2").tobytes()
                        held = au.trim_pcm_silence(pcm, start=True, end=False) if self.s.live_trim_silence else pcm
                        gpu_spoke = bool(held)
                    else:
                        voice = self.voice if k == "copy" and self.voice is not None else alt if k == "stock_alt" and alt else self._stock(lang)
                        await asyncio.wait_for(hosted(voice), voicechain.LATER_TIMEOUT_S)
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # noqa: BLE001 - the next voice is asked
                    fail(k, e)
                    held = b"" if not sent else held
                made = bool(sent or held)
                if self._ladder is not None:
                    self._ladder.note("copied" if k in ("gpu", "copy") else "stock", made)
                if made:
                    timings[f"clone:{lang}"] = int(k in ("gpu", "copy"))
                    if k == "gpu":
                        timings[f"gpu:{lang}"] = 1
                    break
                if not failed or failed[-1]["voice"] != k:
                    fail(k, "made no sound")
        if self._fallback and failed:
            self._voice_event(lang, chunk, [c for c, _ in rest], tried, failed, bool(sent or held), timings,
                              [t for _, t in rest])
        if self._ladder is not None:
            said_by = 0 if gpu_spoke or voice["kind"] == "clone" else 1
            for t in [timings, *[t for _, t in rest]]:
                t[f"rung:{lang}"] = said_by if (sent or held) else 2
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
            tempo = min(max_tempo / spoke_at, want_tempo(len(held) / 2 / sr * 1000))
            if tempo > 1.03:
                try:
                    held = await asyncio.to_thread(au.tempo_pcm, held, sr, tempo)
                except (au.FFmpegError, OSError) as e:
                    log.warning("live tempo fit failed: %s", e)
                    tempo = 1.0
            if tempo * spoke_at > 1.03:
                timings[f"tempo:{lang}"] = round(tempo * spoke_at, 2)
        publish(held)
        if self._dense_log or self._xp is not None:
            kind = "gpu" if gpu_spoke else voice["kind"]
            self._note_dub(lang, kind, chunk, [c for c, _ in rest], text, raw_ms, sent / 2 / sr * 1000, timings)
        if sent:
            # Same rule as the web player: back to back with what is queued, else a jitter buffer after arrival.
            start = max(self._playhead.get(lang, 0), timings[f"t_first_audio:{lang}"] + PLAYER_JITTER_MS)
            if target is not None:  # the player holds it until the video reaches the phrase
                start = max(self._playhead.get(lang, 0), timings[f"t_first_audio:{lang}"] + SYNC_ARRIVE_MS, target)
                timings[f"late:{lang}"] = self._lag[lang] = start - target
                self._late.setdefault(lang, deque(maxlen=500)).append(start - target)
                # Only lateness in making the audio grows the delay; audio queued behind a long phrase does not.
                self._note_late(timings[f"t_first_audio:{lang}"] + SYNC_ARRIVE_MS - target, chunk.seq)
            self._playhead[lang] = start + int(sent / 2 / sr * 1000)
            for c, t in [(chunk, timings), *rest]:
                t[f"t_heard:{lang}"] = start
                t[f"clone:{lang}"] = timings[f"clone:{lang}"]
                self.sess.record_heard(lang, start - c.t_speech_end_ms)
        if self._rec is not None:
            about = {"t_speech_ms": chunk.t_speech_ms, "also": [c.seq for c, _ in rest] or None, **tag}
            if sent:
                self._rec.add(lang, chunk.seq, b"".join(kept), start_ms=start, text=text,
                              late_ms=timings.get(f"late:{lang}") if target is not None else None,
                              hold_ms=delay or None,
                              first_audio_ms=timings[f"t_first_audio:{lang}"] - chunk.t_speech_end_ms,
                              voice="copied" if timings.get(f"clone:{lang}") else "stock",
                              tempo=timings.get(f"tempo:{lang}"), **about)
            else:
                self._rec.skip(lang, chunk.seq, "no_voice", **about)
        end_of_audio()
        timings[f"t_audio_done:{lang}"] = self.sess.now_ms()
        if self._meaning is not None and sent:
            # A sample of the spoken lines is judged against its source afterwards; this phrase is already out.
            src = " ".join(c.text for c in [chunk, *[c for c, _ in rest]])
            if self._meaning.offer(lang, chunk.seq, src, text, bool(timings.get(f"auto:{lang}")) if self._auto
                                   else timings.get(f"budget_ms:{lang}") is not None):
                timings[f"judged:{lang}"] = 1
        self.sess.bus.broadcast({"type": "stats", **self.stats()})

    # ---------- dense speech and the auto budget (app/v1/dense.py) ----------
    def _note_share(self, chunk: Chunk) -> None:
        """The speaking share of the last 30 s, noted with every phrase. Auto mode: over 70% of the time, or over
        `v1_auto_wps_on` words a second, speech is dense (each with a lower threshold to stop being so)."""
        assert self._share is not None
        self._share.add(chunk.t_speech_ms, chunk.t_speech_end_ms)
        now = max(chunk.t_speech_end_ms, self._last_end)
        share = self._share.share(now)
        fast, wps = False, None
        if self._wps is not None:
            self._wps.add(chunk.t_speech_ms, chunk.t_speech_end_ms, len(chunk.text.split()))
            fast, wps = self._wps.fast(now), self._wps.rate(now)
        was, self._dense = self._dense, bool(self._auto and (self._share.dense(now) or fast))
        timings = self._pending[chunk.seq]["timings"]
        if share is not None:
            timings["share"] = round(100 * share)
        if wps is not None:
            timings["wps"] = round(wps, 1)
        if self._dense:
            timings["dense"] = 1
        if was != self._dense and self._trace:
            trace.event("live_dense", session=self.sess.id, seq=chunk.seq, on=self._dense,
                        share=round(100 * share) if share is not None else None,
                        wps=round(wps, 1) if wps is not None else None)
        if self._auto:
            for lang in self.sess.langs:
                self._gate_update(lang, self.sess.now_ms(), chunk.seq)

    def _controller(self, lang: str) -> dense.RateController:
        if lang not in self._ctl:
            self._ctl[lang] = dense.RateController(self.s.v1_ratectrl_kp, self.s.v1_ratectrl_ki,
                                                   self.s.v1_ratectrl_setpoint_ms / 1000, self.s.v1_ratectrl_relax_s,
                                                   self.s.v1_ratectrl_min_scale)
        return self._ctl[lang]

    def _gate(self, lang: str) -> dense.AutoGate:
        if lang not in self._gates:
            self._gates[lang] = dense.AutoGate(self.s.v1_auto_behind_on_ms, self.s.v1_auto_behind_off_ms,
                                               self.s.v1_auto_ratio_on, self.s.v1_auto_ratio_off,
                                               self.s.v1_auto_min_on_ms, self.s.v1_auto_calm_lines)
        return self._gates[lang]

    def _gate_update(self, lang: str, now: int, seq: int, *, backlog_ms: float | None = None,
                     dur_ratio: float | None = None) -> None:
        """Auto budget: one more sign for this language's gate; a change of its answer is logged."""
        g = self._gate(lang)
        change = g.update(now, backlog_ms=backlog_ms, dur_ratio=dur_ratio, dense=self._dense)
        if change is None:
            return
        rec = {"t_ms": now, "seq": seq, "lang": lang, "on": change[0], "why": change[1],
               "backlog_ms": round(g.backlog) if g.backlog is not None else None,
               "dur_ratio": round(g.ratio, 2) if g.ratio is not None else None, "dense": self._dense}
        self.auto_log.append(rec)
        del self.auto_log[:-300]
        log.info("live %s %s: budget %s (%s)", self.sess.id[:8], lang, "on" if change[0] else "off", change[1])
        if self._trace:
            trace.event("live_auto_budget", session=self.sess.id, **rec)

    def _budget_now(self, lang: str) -> bool:
        """Auto budget: does the budget apply to this language's next phrase? Yes while its gate is on, unless
        the meaning check has loosened it all the way (then the language is translated in full)."""
        return self._gate(lang).on and self._loose_steps(lang) < self.s.v1_meaning_max_steps

    def _loose_steps(self, lang: str) -> int:
        return self._meaning.steps(lang) if self._meaning is not None and self._loosen else 0

    def _is_behind(self, lang: str) -> bool:
        """For the meaning check: this language's dub is behind now (its budget may tighten again only then)."""
        g = self._gates.get(lang)
        return bool(g is not None and g.on and g.why in ("behind", "long", "dense"))

    def _voice_kind(self, lang: str) -> str:
        """The kind of voice this language's next line is expected in (the expansion model keeps them apart)."""
        if self._gpu_speaks(lang) or self._gpu_planned(lang):
            return "gpu"
        return "clone" if self.voice is not None and lang in self.clone_langs else "stock"

    def _budget_plan(self, lang: str, chunk: Chunk, behind: int) -> dict[str, Any] | None:
        """The budget: this phrase's slot as a length for the translator, or None when nothing is known yet of
        this voice in this language (then v0's word limit applies).

        The slot is the phrase's own span. Auto mode: the scale comes from the controller (at most
        `v1_dense_scale` while speech is dense), plus `v1_meaning_step` for every step the meaning check has
        loosened this language by. Manual mode: from how far behind the dub is, in two steps."""
        if self._xp is None:
            return None
        n_src = len(chunk.text.split())
        slot = chunk.t_speech_end_ms - chunk.t_speech_ms
        if not PACE_MS[0] * n_src <= slot <= PACE_MS[1] * n_src:   # a span that is not believed: the speaker's pace
            slot = int(n_src * self._src_ms_per_word)
        loose = 0
        if self._auto:
            scale = self._controller(lang).scale
            if self._dense:
                scale = min(scale, self.s.v1_dense_scale)
            loose = self._loose_steps(lang)
        else:
            scale = 1.0 if behind <= self.s.live_brief_after_ms else self.s.v1_budget_behind_scale if behind <= 2000 \
                else self.s.v1_budget_far_scale
        kind = self._voice_kind(lang)
        delay = self.sync_delay()
        if delay:
            # A line that arrives late (a long utterance the recogniser did not let go of) cannot start on its
            # moment any more. It gets the time that is left until the next phrase is due, not its whole slot,
            # so the phrase after it does not pay for it. Never under the controller's floor.
            begin = max(self.sess.now_ms() + BUDGET_LEAD_MS, chunk.t_speech_ms + delay)
            room = chunk.t_speech_end_ms + delay - begin
            if room < slot * scale:
                scale = max(self.s.v1_ratectrl_min_scale, room / max(1, slot))
        # What the meaning check has loosened this language by comes on top, also over a line's own room: that
        # the dub may then run a little long is the price of saying what was said.
        scale += loose * self.s.v1_meaning_step
        plan = dense.plan(self._xp, lang, kind, slot, scale, self.s.v1_budget_share)
        if plan is None:
            return None
        plan["kind"] = kind
        if kind == "gpu" and self.s.gpu_voice_guard and plan["max_words"] <= self.s.gpu_voice_short_words:
            # The engine is asked to say a line this short more slowly (it swallows short lines otherwise).
            plan["max_chars"] = max(6, int(plan["max_chars"] * self.s.gpu_voice_short_speed))
        if chunk.seq in self._pending:
            t = self._pending[chunk.seq]["timings"]
            t[f"budget:{lang}"], t[f"budget_chars:{lang}"] = plan["max_words"], plan["max_chars"]
            t[f"budget_ms:{lang}"], t[f"ctl:{lang}"] = plan["target_ms"], plan["scale"]
            if loose:
                t[f"loose:{lang}"] = loose
        return plan

    async def _within_budget(self, lang: str, chunk: Chunk, text: str, plan: dict[str, Any]) -> str:
        """The budget: the translation's expected duration against its slot. More than `v1_budget_over`
        times the slot: one quick request for a shorter line, used when it is shorter and well formed."""
        assert self._xp is not None
        t = self._pending[chunk.seq]["timings"] if chunk.seq in self._pending else {}
        est = self._expected_ms(lang, plan["kind"], text)
        t[f"est_ms:{lang}"] = t[f"est0_ms:{lang}"] = int(est)   # est0: the first answer, est: the line spoken
        words = len(text.split())
        if est <= plan["target_ms"] * self.s.v1_budget_over or words < 4:
            return text
        want = dense.shorter_words(words, est, plan["target_ms"])
        t[f"reasked:{lang}"] = 1
        try:
            out = await asyncio.wait_for(self.llm.shorten(text, lang, plan["target_ms"] / 1000, max_words=want),
                                         self.s.v1_budget_reask_timeout_s)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - the first answer is spoken
            log.info("live budget: no shorter line (%s)", str(e)[:120])
            return text
        out = (out or "").strip()
        from app.providers.llm_local import has_latin
        from app.providers.llm_openai import SCRIPTS, wrong_script
        bad = not out or wrong_script(out, lang) or (plan["kind"] == "gpu" and lang in SCRIPTS and has_latin(out))
        if bad or dense.letters(out) >= dense.letters(text):
            return text
        t[f"reasked:{lang}"] = 2   # the shorter line is the one spoken
        t[f"est_ms:{lang}"] = int(self._expected_ms(lang, plan["kind"], out))
        return out

    def _expected_ms(self, lang: str, kind: str, text: str) -> float:
        """How long the voice will take for this line: letters times this voice's ms a letter, and more for a
        line so short that our engine is asked to say it slowly."""
        assert self._xp is not None
        est = self._xp.estimate_ms(lang, kind, text) or 0.0
        if kind == "gpu" and self.s.gpu_voice_guard and 0 < len(text.split()) <= self.s.gpu_voice_short_words:
            est /= max(0.4, self.s.gpu_voice_short_speed)
        return est

    def _note_dub(self, lang: str, kind: str, chunk: Chunk, also: list[Chunk], text: str, raw_ms: float,
                  dub_ms: float, timings: dict[str, Any]) -> None:
        """After a line was made: its length against its slot (dur_ratio), and one more line for the expansion
        model. `raw_ms` is the speech at the voice's own pace, `dub_ms` what was sent (after any speed-up)."""
        if dub_ms <= 0:
            return
        last = also[-1] if also else chunk
        slot = max(1, last.t_speech_end_ms - chunk.t_speech_ms)
        src_words = sum(len(c.text.split()) for c in [chunk, *also])
        words, chars = len(text.split()), dense.letters(text)
        if self._xp is not None:
            self._xp.note(lang, kind, src_words, words, chars, raw_ms)
        if self._dense_log:
            timings[f"dub_ms:{lang}"], timings[f"dub_raw_ms:{lang}"] = int(dub_ms), int(raw_ms)
            timings[f"slot_ms:{lang}"] = slot
            timings[f"dur_ratio:{lang}"] = dense.dur_ratio(dub_ms, slot)
            timings[f"tgt_words:{lang}"], timings[f"tgt_chars:{lang}"] = words, chars
            if self._auto:
                self._gate_update(lang, self.sess.now_ms(), chunk.seq, dur_ratio=timings[f"dur_ratio:{lang}"])

    def dense_stats(self) -> dict[str, Any]:
        """For the session's metrics: dense speech, each language's budget gate and controller, the meaning
        check, the guards, the lines another voice spoke or no voice spoke, the expansion model as it stands."""
        out: dict[str, Any] = {}
        if self._auto:
            out["dense"] = self._dense
            out["ratectrl"] = {lg: {"scale": round(c.scale, 2), "integral": round(c.integral, 2),
                                    "backlog_s": round(c.backlog_s, 2)} for lg, c in self._ctl.items()}
            out["auto_budget"] = {lg: {"on": g.on, "why": g.why,
                                       "backlog_ms": round(g.backlog) if g.backlog is not None else None,
                                       "dur_ratio": round(g.ratio, 2) if g.ratio is not None else None,
                                       "loose_steps": self._loose_steps(lg)} for lg, g in self._gates.items()}
            out["auto_budget_log"] = list(self.auto_log)
        if self._meaning is not None:
            out["meaning"] = self._meaning.stats()
        if self._script_guard:
            out["guard"] = dict(self.guard)
        if self._fallback:
            out["unspoken"] = self.unspoken
            out["voice_events"] = list(self.voice_events)
        if self._xp is not None:
            out["expansion"] = self._xp.state()
        return out

    # ---------- v1.2: guards, and lines a voice refused ----------
    async def _script_checked(self, lang: str, chunk: Chunk, text: str, ctx: list[str], native: bool) -> str:
        """The script guard, on every translated line: letters that are neither Latin nor of the target
        language's script. A line that fails is translated once more (plainly, a few seconds at most); when that
        fails too the first answer is spoken and the line is flagged (`script:<lang>` 2; 1 = the second answer
        was used). It sees letters only: a Hindi word in Tamil letters passes."""
        self.guard["script_checked"] += 1
        if not wrong_script(text, lang):
            return text
        self.guard["script_failed"] += 1
        t = self._pending[chunk.seq]["timings"] if chunk.seq in self._pending else {}
        again = ""
        try:
            kw: dict[str, Any] = {"native": True} if native else {}
            again = await asyncio.wait_for(self.llm.translate_chunk(chunk.text, lang, self.glossary, ctx, **kw),
                                           GUARD_REDO_TIMEOUT_S)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - the first answer stands, flagged
            log.info("live script guard: no second answer (%s)", str(e)[:120])
        ok = bool(again) and not wrong_script(again, lang)
        self.guard["script_regenerated" if ok else "script_flagged"] += 1
        t[f"script:{lang}"] = 1 if ok else 2
        log.warning("live %s %s: phrase %d was in the wrong script, %s", self.sess.id[:8], lang, chunk.seq,
                    "translated again" if ok else "translated again and still wrong: flagged")
        if self._trace:
            trace.event("live_guard_script", session=self.sess.id, seq=chunk.seq, lang=lang, regenerated=ok)
        return again if ok else text

    def _voice_event(self, lang: str, chunk: Chunk, also: list[Chunk], tried: list[str], failed: list[dict[str, str]],
                     spoken: bool, timings: dict[str, Any], rest: list[dict[str, Any]]) -> None:
        """A voice refused, failed or made nothing for this line. Either another voice spoke it (`voice_fb`: the
        voices asked, in order; the last one spoke) or none did (`unspoken`). Never silent: marked on the phrase,
        counted, in the trace and in the log."""
        chain = ">".join(tried)
        for t in [timings, *rest]:
            if spoken:
                t[f"voice_fb:{lang}"] = chain
            else:
                t[f"unspoken:{lang}"] = "no_voice"
        if not spoken:
            self.unspoken += 1
        rec = {"t_ms": self.sess.now_ms(), "seq": chunk.seq, "lang": lang, "tried": list(tried), "failed": list(failed),
               "spoken_by": tried[-1] if spoken and tried else None, **({"also": [c.seq for c in also]} if also else {})}
        self.voice_events.append(rec)
        del self.voice_events[:-300]
        if spoken:
            log.warning("live %s %s: phrase %d: %s made nothing, spoken by %s", self.sess.id[:8], lang, chunk.seq,
                        ", ".join(f"{f['voice']} ({f['error']})" for f in failed), rec["spoken_by"])
        else:
            log.error("live %s %s: phrase %d has NO SOUND: every voice failed: %s", self.sess.id[:8], lang, chunk.seq,
                      ", ".join(f"{f['voice']} ({f['error']})" for f in failed))
            self.sess.bus.publish(ALL, {"type": "error", "message": f"{lang}: no voice could say a line ({chain})"},
                                  to_all=False)
        if self._trace:
            trace.event("live_voice_fallback", session=self.sess.id, **rec)

    def _mark_unspoken(self, lang: str, chunks: list[Chunk], why: str) -> None:
        """A line that gets no sound for a reason other than a voice (its translation failed, an error in the
        pipeline): marked and counted like the others, so no line is ever silent without a record."""
        if not self._fallback:
            return
        for c in chunks:
            if c.seq in self._pending:
                self._pending[c.seq]["timings"].setdefault(f"unspoken:{lang}", why)
        self.unspoken += 1
        rec = {"t_ms": self.sess.now_ms(), "seq": chunks[0].seq, "lang": lang, "tried": [], "failed": [],
               "spoken_by": None, "why": why}
        self.voice_events.append(rec)
        log.error("live %s %s: phrase %d has NO SOUND (%s)", self.sess.id[:8], lang, chunks[0].seq, why)
        if self._trace:
            trace.event("live_voice_fallback", session=self.sess.id, **rec)

    # ---------- v1 (each used only with its flag on) ----------
    def _gpu_blocked(self) -> bool:
        """Every engine of the copied voice has its circuit open (`V1_BREAKER`); False when there are no breakers."""
        brs = getattr(self.gpu, "breakers", None)
        return bool(brs) and all(b.blocked() for b in brs)

    def _wants_stored(self) -> bool:
        row = self.sess.row
        return bool(row.get("streamer_id") and row.get("voice_mode") == "clone" and self.gpu.enabled)

    def _voice_may_try(self, lang: str) -> bool:
        """`V1_LIVE_DEGRADE`: is a voice asked for this line? Yes while one answers; with none, now and then."""
        assert self._ladder is not None
        if self._gpu_speaks(lang) and not self._gpu_blocked() and not self._ladder.down("copied"):
            return True
        return self._ladder.may_try("stock")

    def rung(self) -> tuple[int, str]:
        """`V1_LIVE_DEGRADE`: where on the ladder this session stands now, and why it is not higher."""
        assert self._ladder is not None
        consent = self.sess.row.get("voice_from_stream") or {}
        wants = bool(self.voice is not None or self._wants_stored() or self._gpu_stored
                     or (consent.get("consent_at") and (self.gpu.enabled or self._enrol is not None)))
        ready = self.gpu_ready or self.voice is not None
        up = (self._gpu_up() and not self._gpu_blocked()) if self.gpu_ready else True
        return self._ladder.level(wants_copied=wants, copied_ready=ready, copied_up=up)

    def _rung_tick(self) -> dict[str, Any]:
        """Once a second: note a change of rung (viewers, trace, log), ask again for a stored voice that did not
        load, and give the rung to the clock message, so a viewer who joins later knows it too."""
        now = self.sess.now_ms()
        level, why = self.rung()
        if self._rung is None or self._rung[0] != level:
            was = RUNGS[self._rung[0]] if self._rung is not None else None
            self.rungs.append({"t_ms": now, "rung": RUNGS[level], "why": why})
            del self.rungs[:-200]
            if was is not None:
                log.warning("live %s: %s -> %s (%s)", self.sess.id[:8], was, RUNGS[level], why or "back")
                self.sess.bus.broadcast({"type": "degrade", "rung": RUNGS[level], "was": was, "why": why, "t_ms": now})
                if self._trace:
                    trace.event("live_degrade", session=self.sess.id, rung=RUNGS[level], was=was, why=why, t_ms=now)
        self._rung = (level, why)
        if (self._wants_stored() and not self._gpu_stored and not self._stored_busy and not self._gpu_blocked()
                and now - self._stored_try_at >= 15000):
            self._stored_busy, self._stored_try_at = True, now
            self.tasks.append(asyncio.create_task(self._stored_again()))
        return {"rung": RUNGS[level]}

    async def _stored_again(self) -> None:
        try:
            await self._use_stored_voice()
        finally:
            self._stored_busy = False

    def degrade_stats(self) -> dict[str, Any]:
        """For the session's metrics: the rung now and every change. Empty with the flag off."""
        if self._ladder is None:
            return {}
        level, why = self._rung if self._rung is not None else self.rung()
        return {"rung": RUNGS[level], "rung_why": why, "rung_changes": list(self.rungs)}

    async def _shorter(self, lang: str, text: str, late_by: int, limit: int) -> str | None:
        """`V1_LIVE_LATE_SHORTEN`: a version of a late line with about 40% of its words, or None (then it is
        skipped as before): when it is later than `v1_late_skip_factor` times the limit, or no shorter line came."""
        n = len(text.split())
        if late_by > limit * self.s.v1_late_skip_factor or n < 5:
            return None
        want = max(3, round(n * 0.4))
        try:
            out = await asyncio.wait_for(self.llm.shorten(text, lang, want * 0.45, max_words=want), 4.0)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("live shorten failed: %s", e)
            return None
        out = (out or "").strip()
        return out if out and len(out.split()) < n else None

    async def _hear_back(self, lang: str, text: str, pcm: bytes, rate: int) -> float | None:
        """Share of a dubbed line's words that the scorer hears back (0-1), or None when there is no scorer."""
        if self._stages is None:
            from app.v1.stages import Stages
            self._stages = Stages("live", self.engine or "cloud", key=self.sess.id)
        if not self._stages.names("score"):
            return None
        wav = Path(tempfile.gettempdir()) / f"bd_v1_check_{self.sess.id}_{lang}_{self.sess.now_ms()}.wav"
        try:
            audio = np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0
            await asyncio.to_thread(au.write_wav, wav, audio, rate)
            got = await asyncio.wait_for(self._stages.score(wav, text, lang), 4.0)
            return float(got["backcheck"]) if got.get("backcheck") is not None else None
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - no verdict
            log.info("live back-check: no verdict (%s)", str(e)[:120])
            return None
        finally:
            wav.unlink(missing_ok=True)

    async def _checked(self, lang: str, text: str, pcm: bytes, rate: int, speed: float, target: int | None,
                       timings: dict[str, Any]) -> tuple[bytes, int]:
        """`V1_LIVE_BACKCHECK`: hear the line back. With time to spare before it is due, a line that came out
        wrong is made once more and the better one is kept; without it, the score is only recorded."""
        room = target - self.sess.now_ms() if target is not None else 0
        if room < 2500:
            async def later() -> None:
                score = await self._hear_back(lang, text, pcm, rate)
                if score is not None:
                    timings[f"backcheck:{lang}"] = round(score, 2)
            self.tasks.append(asyncio.create_task(later()))
            return pcm, rate
        score = await self._hear_back(lang, text, pcm, rate)
        if score is None:
            return pcm, rate
        timings[f"backcheck:{lang}"] = round(score, 2)
        if score >= self.s.v1_backcheck_min or target is None or target - self.sess.now_ms() < 1500:
            return pcm, rate
        try:
            pcm2, rate2 = await self.gpu.synth(self._gpu_sid or self.sess.id, text, lang, speed=speed)
        except Exception as e:  # noqa: BLE001 - the first version is spoken
            log.info("live back-check: second version failed (%s)", str(e)[:120])
            return pcm, rate
        again = await self._hear_back(lang, text, pcm2, rate2) if target - self.sess.now_ms() >= 1200 else None
        if again is None or again > score:
            timings[f"redone:{lang}"] = 1
            if again is not None:
                timings[f"backcheck:{lang}"] = round(again, 2)
            return pcm2, rate2
        return pcm, rate

    async def _chunk_done(self, seq: int) -> None:
        p = self._pending.get(seq)
        if not p:
            return
        p["left"] -= 1
        if p["left"] > 0:
            return
        self._pending.pop(seq, None)
        if self._trace:
            fb = getattr(self.stt, "fell_back", 0)
            if fb != getattr(self, "_stt_fb_seen", 0):
                self._stt_fb_seen, p["timings"]["stt_fb"] = fb, 1
            trace.live_phrase(self.sess.id, self.sess.row, seq, p, {
                "stt": trace.provider_name(self.stt), "llm": trace.provider_name(self.llm)})
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
