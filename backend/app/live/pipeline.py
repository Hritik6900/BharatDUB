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
from app.providers import get_gpu_voice, get_llm, get_stt, get_tts
from app.providers.base import ProviderError, VoiceSpec
from app.shared import audio_utils as au
from app.shared.metrics import percentile
from app.v1 import apilog, breaker, dense, hold, record, trace, warm
from app.v1.degrade import RUNGS, Ladder
from app.v1.phrase import DynamicPhraser, ShortLineMerger

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
# `V1_LIVE_WARMSTART`: the first two words of each check line, for one short line on our voice engine.
WARM_LINES = {lg: " ".join(line.split()[:2]) for lg, line in GPU_CHECK_LINES.items()}
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


def prefetch_stored_voice(sess: LiveSession) -> None:
    """`V1_LIVE_WARMSTART`: when a streamer's session is created, their recorded voice is sent to the engines at
    once, not when the sound starts to arrive; the session's start then finds it there. Nothing without the flag,
    and nothing for a session that has no stored voice (the consent check is `send_stored_voice`'s and the engine
    client's own)."""
    row = sess.row
    if not (get_settings().v1_live_warmstart and row.get("streamer_id") and row.get("voice_mode") == "clone"):
        return
    eng = row.get("engine") or None
    gpu, stt = (get_gpu_voice(eng), get_stt(eng)) if eng else (get_gpu_voice(), get_stt())
    t0 = sess.now_ms()

    async def go() -> tuple[str, Any, int] | None:
        got = await send_stored_voice(row, gpu, stt)
        return (*got, sess.now_ms() - t0) if got else None
    sess.prefetch = asyncio.create_task(go())
    sess.prefetch.add_done_callback(lambda t: t.cancelled() or t.exception())   # read at the start, or not at all


class LivePipeline:
    def __init__(self, sess: LiveSession, stt: Any = None, llm: Any = None, tts: Any = None,
                 gpu: Any = None) -> None:
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
        self._trace = self.s.v1_trace   # v1: extra timing marks and one trace record per phrase
        self.audio: asyncio.Queue[bytes | None] = asyncio.Queue()
        self.assembler = Assembler()
        self.phraser = Phraser(self.s.live_phrase_min_words, self.s.live_phrase_max_words)
        # v1, each behind its flag (off = the lines below change nothing and the pipeline is v0's).
        self._merger: ShortLineMerger | None = None
        if self.s.v1_phrase_dynamic:
            self.phraser = DynamicPhraser((self.s.v1_first_phrase_min_words, self.s.v1_first_phrase_max_words),
                                          (self.s.v1_phrase_min_words, self.s.v1_phrase_max_words))
            self._merger = ShortLineMerger(self.s.v1_merge_under_words, self.s.v1_merge_wait_ms)
        self._stages: Any = None   # the scorer for the live back-check, made when first needed
        # `V1_LIVE_DEGRADE`: the ladder (copied voice, stock voice, captions only, original sound). None = off.
        self._ladder = Ladder(sess.now_ms, fails=self.s.v1_degrade_fails,
                              probe_ms=self.s.v1_degrade_probe_ms) if self.s.v1_live_degrade else None
        self._rung: tuple[int, str] | None = None
        self.rungs: list[dict[str, Any]] = []   # every change of rung: {t_ms, rung, why}
        self._stored_busy = False
        self._stored_try_at = 0
        # v1.1 dense speech (app/v1/dense.py). `_dense_log`: dur_ratio, backlog and the rest are noted per phrase.
        self._dense_log = bool(self._trace or self.s.v1_live_budget or self.s.v1_live_ratectrl)
        self._xp = dense.ExpansionModel.load() if (self.s.v1_live_budget or self.s.v1_live_native_speed) else None
        self._ctl: dict[str, dense.RateController] = {}   # `V1_LIVE_RATECTRL`: one controller per language
        self._share = dense.SpeakingShare(self.s.v1_dense_window_ms, self.s.v1_dense_share, self.s.v1_dense_off_share) \
            if self._dense_log else None
        self._dense = False   # dense mode is on (only ever with `V1_LIVE_RATECTRL`)
        if self.s.v1_live_ratectrl and self._merger is None:   # dense mode joins short lines to the next
            self._merger = ShortLineMerger(self.s.v1_dense_merge_under_words, self.s.v1_merge_wait_ms)
        # v1.1 session start (`V1_LIVE_WARMSTART`) and the one English voice (`V1_EN_SINGLE_VOICE`); app/v1/warm.py.
        self._warm = bool(self.s.v1_live_warmstart)
        self._pitch = warm.PitchTracker() if self._warm else None   # the speaker's pitch, for the stock voice
        self._stock_pick: dict[str, dict[str, Any]] = {}   # per language: the stock voice chosen once and kept
        self._stock_level: dict[str, float] = {}           # per language: how loud the opening stock lines were
        self._handover: dict[str, int] = {}                # per language: copied lines softened after them
        self._opening: dict[str, int] = {}                 # per language: stock lines spoken while the copy was awaited
        self._copy_coming = False                          # the hosted copy is being learned from the stream
        self._en_mode: str | None = None                   # "copy" | "stock" for English; None = flag off or not that session
        self.warm_ms: dict[str, Any] = {}                  # what each warm-up call took
        self.en_retries = [0, 0]                           # English lines asked a second time, and how many then came
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
        if self.s.v1_breaker:
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
        if self.s.v1_en_single_voice and self.engine == "gpu" and EN in self.sess.langs:
            # One English voice for the whole session, decided here and never changed (app/v1/warm.py).
            self._en_mode = warm.en_mode(self.s.v1_en_voice)
            if self._trace:
                trace.event("live_en_voice", session=self.sess.id, mode=self._en_mode, setting=self.s.v1_en_voice,
                            copy_at_start=self.voice is not None)
        if self._rec is not None:
            self._rec.start()
            if self._trace:
                trace.event("live_record", session=self.sess.id, langs=len(self.sess.langs))
        self.tasks = [asyncio.create_task(self._stt_loop()), asyncio.create_task(self._poll_loop())]
        if self._warm and self.sess.langs:
            self.tasks.append(asyncio.create_task(self._warmstart()))
        elif self.s.live_warmup and self.sess.langs:
            self.tasks.append(asyncio.create_task(self._warmup()))
        self.tasks += [asyncio.create_task(self._worker(lg)) for lg in self.sess.langs]

    async def stop(self) -> None:
        if not self.running:
            return
        self.running = False
        if self.s.v1_breaker:
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
        if self._rec is not None:
            self._rec.close()
        if self._trace:
            trace.event("live_session_end", session=self.sess.id, phrases=self.sess.chunk_count,
                        engine=self.sess.row.get("engine") or "cloud", hold_ms=self._sync_delay,
                        hold_grown=len(self.sync_grown),
                        hold_eased=len(self._ease.steps) if self._ease is not None else None,
                        merged=self._merger.merged if self._merger else None,
                        short_alone=self._merger.alone if self._merger else None)

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

    async def _warmstart(self) -> None:
        """`V1_LIVE_WARMSTART`, in place of `_warmup`: every target language and every engine that will speak is
        asked once before the first phrase.
          - one tiny translation per language (v0: the first language only);
          - our voice engines: each process is asked for its state (opens its connection); with a stored voice
            on them, one tiny line per language and at least one per process (v0: nothing);
          - the hosted voice: one tiny line per language it will speak at the start, also the languages our engine
            takes over later, whose opening is in a stock voice (v0: only when no copied voice is coming, and
            only the first language). English in the hosted copy is asked in that copy when the session has it."""
        t0 = self.sess.now_ms()
        langs = self.sess.langs

        async def timed(name: str, job: Any, limit: float = TRANSLATE_TIMEOUT_S) -> None:
            t = self.sess.now_ms()
            try:
                await asyncio.wait_for(job, limit)
                self.warm_ms[name] = self.sess.now_ms() - t
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - only a warm-up
                self.warm_ms[name] = f"failed: {type(e).__name__}"

        async def translation(lang: str) -> None:
            kw: dict[str, Any] = {"native": True} if self._gpu_planned(lang) else {}
            await self.llm.translate_chunk("नमस्ते", lang, [], [], **kw)

        async def engines() -> None:
            health = getattr(self.gpu, "health", None)
            if not (self.gpu.enabled and health is not None):
                return
            await timed("engines", health())
            mine = [lg for lg in langs if self._gpu_speaks(lg)]
            if mine:   # a stored voice is on the engines: one short line per language, every process at least once
                n = max(len(mine), int(getattr(self.gpu, "capacity", 1)))
                await timed("engine_lines", asyncio.gather(*(
                    self.gpu.synth(self._gpu_sid or self.sess.id, WARM_LINES.get(mine[i % len(mine)], "ok"), mine[i % len(mine)])
                    for i in range(n))))

        async def hosted_line(lang: str) -> None:
            voice: VoiceSpec = {"kind": "stock", "voice": VOICE_BY_LANG.get(lang, VOICE_BY_LANG["hi-IN"])}
            if self.voice is not None and lang == EN and self._en_mode == "copy":
                voice = self.voice
            async with self._voice_turn:   # one request at a time on the hosted account; a real phrase waits its turn
                async for _ in self.tts.synth_stream("ok", lang, voice, sample_rate=self.s.live_sample_rate):
                    pass

        async def hosted() -> None:
            for lang in langs:
                if not self._gpu_speaks(lang) and self.running:
                    await timed(f"voice:{lang}", hosted_line(lang))

        await asyncio.gather(*(timed(f"translate:{lg}", translation(lg)) for lg in langs), engines(), hosted())
        self.warm_ms["total"] = self.sess.now_ms() - t0
        if self._trace:
            trace.event("live_warmstart", session=self.sess.id, **{k.replace(":", "_"): v for k, v in self.warm_ms.items()})

    def warm_stats(self) -> dict[str, Any]:
        """For the session's metrics: the session's start and the English voice. Empty with both flags off."""
        out: dict[str, Any] = {}
        if self._warm:
            f0 = self._pitch.median_hz() if self._pitch is not None else None
            out["warm"] = {"calls_ms": dict(self.warm_ms), "f0_hz": round(f0) if f0 else None,
                           "speaker": self._pitch.gender() if self._pitch is not None else None,
                           "stock_voice": {lg: dict(v) for lg, v in self._stock_pick.items()},
                           "opening_stock_lines": dict(self._opening),
                           "softened_lines": dict(self._handover)}
        if self._en_mode is not None:
            out["en_voice"] = self._en_mode
            out["en_lines_asked_again"], out["en_lines_then_spoken"] = self.en_retries
        return out

    async def _use_stored_voice(self) -> None:
        """Streamer Mode: the voice the streamer recorded (with consent) goes to the GPU engines before the first
        word, so the first phrase is already in their voice. It is not replaced during the stream."""
        t0 = self.sess.now_ms()
        got: tuple[str, Any] | None = None
        ahead, self.sess.prefetch = getattr(self.sess, "prefetch", None), None
        if ahead is not None:   # `V1_LIVE_WARMSTART`: sent when the session was created
            try:
                sent_ahead = await ahead
                if sent_ahead is not None:
                    got, self.warm_ms["stored_voice_ahead"] = (sent_ahead[0], sent_ahead[1]), sent_ahead[2]
            except Exception as e:  # noqa: BLE001 - sent again below, as without the prefetch
                log.info("live stored voice: the prefetch did not finish (%s)", str(e)[:120])
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
        if self._pitch is not None and not self._pitch.done:
            self._pitch.add(pcm)
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
            # `V1_EN_SINGLE_VOICE`: never chosen line by line. The copy, once the session has it and while it
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
        """The stock voice of a language. With `V1_LIVE_WARMSTART`: the one nearest to the speaker's pitch,
        chosen at the language's first stock line and kept for the session."""
        if self._pitch is None:
            return {"kind": "stock", "voice": VOICE_BY_LANG.get(lang, VOICE_BY_LANG["hi-IN"])}
        pick = self._stock_pick.get(lang)
        if pick is None:
            f0 = self._pitch.median_hz()
            pick = self._stock_pick[lang] = {**warm.pick_stock(lang, self._pitch.gender()),
                                             "f0_hz": round(f0) if f0 else None, "t_ms": self.sess.now_ms()}
            if self._trace:
                trace.event("live_stock_voice", session=self.sess.id, lang=lang, **pick)
        return {"kind": "stock", "voice": pick["voice"]}

    def _stock_failed(self, lang: str) -> None:
        """A matched voice that made nothing (a name the service does not know): the language's usual voice from
        now on."""
        pick = self._stock_pick.get(lang)
        usual = VOICE_BY_LANG.get(lang, VOICE_BY_LANG["hi-IN"])
        if pick is not None and pick["voice"] != usual:
            log.warning("live %s: stock voice %s made nothing, back to %s", lang, pick["voice"], usual)
            pick.update(voice=usual, matched=False, note=f"{pick['voice']} did not answer")

    def _awaiting_copy(self, lang: str) -> bool:
        """A copied voice is on its way for this language and not there yet (the opening of a session)."""
        if self._gpu_planned(lang):
            return not self.gpu_ready
        return self._copy_coming and (lang in self.clone_langs or (self._en_mode == "copy" and lang == EN))

    def _soften(self, lang: str, pcm: bytes, sr: int, copied: bool, timings: dict[str, Any]) -> bytes:
        """`V1_LIVE_WARMSTART`: the change from the opening's stock voice to the copied one, softened. Lines are
        separate utterances, so nothing overlaps: every stock line of the opening ends in a short fade (any of
        them may be the last), the first copied line begins with one, and the first copied lines are brought
        part of the way to the level the stock voice spoke at."""
        if not copied:
            if not self._awaiting_copy(lang):
                return pcm
            lv = warm.level(pcm)
            if lv:
                prev = self._stock_level.get(lang)
                self._stock_level[lang] = lv if not prev else 0.5 * prev + 0.5 * lv
            self._opening[lang] = self._opening.get(lang, 0) + 1
            timings[f"open:{lang}"] = 1
            return warm.fade(pcm, sr, self.s.v1_warm_fade_ms, out=True)
        n, lines = self._handover.get(lang, 0), max(0, self.s.v1_warm_level_lines)
        if lang not in self._stock_level or n >= max(1, lines):
            return pcm
        self._handover[lang] = n + 1
        timings[f"handover:{lang}"] = n + 1
        if n < lines:
            pcm = warm.toward(pcm, warm.level(pcm), self._stock_level[lang], 1 - (n + 1) / (lines + 1))
        if n == 0:
            pcm = warm.fade(pcm, sr, self.s.v1_warm_fade_ms, out=False)
        return pcm

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
            chunk = self.assembler.poll(self.sess.now_ms())
            if chunk:
                self._dispatch(chunk)
            if self._merger is not None:
                alone = self._merger.poll(self.sess.now_ms())
                if alone:
                    self._dispatch(alone, True)

    # ---------- fan-out ----------
    def _dispatch(self, chunk: Chunk, merged: bool = False) -> None:
        if self._merger is not None and not merged and (self.s.v1_phrase_dynamic or self._dense
                                                        or self._merger.held is not None):
            # v1: a line of one or two words waits for the next line and goes out as part of it.
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
            plan = self._budget_plan(lang, chunk, behind) if self.s.v1_live_budget else None
            if plan is not None:
                # v1.1: the phrase's own slot as words and letters; the answer is checked below.
                kw = {"max_words": plan["max_words"], "max_chars": plan["max_chars"], "compact": True}
                if plan["scale"] < 0.8:
                    kw["brief"] = True
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
                    if self._warm and not self._gpu_busy:
                        # `V1_LIVE_WARMSTART`: no sample is on its way to the engines, so nothing says the voice is
                        # near (measured 25 Nov 2026 with the wait: 0 of 27 lines of a session's first three
                        # phrases got the copied voice by waiting). The matched stock voice speaks now.
                        break
                    await asyncio.sleep(0.1)
            if self._en_mode == "copy" and lang == EN and self.voice is None and self._copy_coming and self.sync_delay():
                # `V1_EN_SINGLE_VOICE`: the same for the hosted copy of English, which takes longer to make.
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
            if self._ladder is not None:
                timings[f"rung:{lang}"] = 3
            if self._rec is not None:
                self._rec.skip(lang, chunk.seq, "untranslated", t_speech_ms=chunk.t_speech_ms)
            end_of_audio()
            return
        if self._trace:
            timings[f"tts_chars:{lang}"] = len(text)
        gpu_spoke = False   # this line came from our voice engine
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
            if self.s.v1_live_ratectrl:
                ctl = self._controller(lang)
                ctl.update(backlog / 1000, now / 1000)
                timings[f"ctl_i:{lang}"] = round(ctl.integral, 2)
                if self._dense:
                    max_tempo = max(max_tempo, self.s.v1_dense_max_tempo)
        # With one Gnani request at a time, every line spoken delays the next one. Audio nobody is tuned to,
        # or that would be heard too late to feel live, is not made; its caption has already gone out.
        unheard = self.s.live_tts_only_heard and not bus.listeners(lang)
        too_late = -spare > self.s.live_sync_late_skip_ms if target is not None else lag_ms > self.s.live_skip_after_ms
        if too_late and not unheard and self.s.v1_live_late_shorten:
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
                    elif fit and self.s.v1_live_native_speed and self._xp is not None:
                        # v1.1: the line's expected duration (ms a letter of this voice) against its room. The
                        # engine is asked for part of the speed-up, never for speech under the pace floor;
                        # what is still missing is done by tempo afterwards, as before.
                        n_words = len(text.split())
                        est = self._xp.estimate_ms(lang, "gpu", text)
                        if est and n_words > self.s.gpu_voice_short_words:
                            factor = min(self.s.v1_native_max, want_tempo(est), est / n_words / self.s.v1_native_floor_ms)
                            if factor > 1.03:
                                speed = base * factor
                                timings[f"native:{lang}"] = round(factor, 2)
                    pcm, rate = await self.gpu.synth(self._gpu_sid or self.sess.id, text, lang, speed=speed)
                    if self.s.v1_live_backcheck:
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
                    if self._trace:
                        timings[f"tts_fb:{lang}"] = 1
            if self._en_mode is None or lang != EN:
                await hosted(voice)
                return
            # `V1_EN_SINGLE_VOICE`: a line the hosted voice refused before any sound (seen 25 Nov 2026: one stock
            # line in three answered "technical difficulties", HTTP 502, within 0.2 s) is asked once more in the
            # same voice, instead of being left out. The streamed call has no retry of its own.
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
            bus.publish(ALL, {"type": "error", "message": f"{lang} voice failed: {str(e)[:120]}"}, to_all=False)
        except Exception as e:  # noqa: BLE001 - e.g. the hosted voice's connection dropped mid-line
            if self._ladder is None:
                raise   # as before: the worker closes the phrase
            log.warning("live %s voice failed: %s: %s", lang, type(e).__name__, str(e)[:120])
        if self._ladder is not None:
            if not gpu_spoke:
                made = bool(sent or held)
                self._ladder.note("copied" if voice["kind"] == "clone" else "stock", made)
                if not made and voice["kind"] == "clone":
                    # The hosted copy of the voice did not answer: a stock voice says this line.
                    voice = self._stock(lang)
                    timings[f"clone:{lang}"] = 0
                    try:
                        await asyncio.wait_for(hosted(voice), TTS_TIMEOUT_S)
                    except Exception as e:  # noqa: BLE001 - no voice for this line; its caption is out
                        bus.publish(ALL, {"type": "error", "message": f"{lang} voice failed: {str(e)[:120]}"}, to_all=False)
                    self._ladder.note("stock", bool(sent or held))
            said_by = 0 if gpu_spoke or voice["kind"] == "clone" else 1
            for t in [timings, *[t for _, t in rest]]:
                t[f"rung:{lang}"] = said_by if (sent or held) else 2
        if self._pitch is not None and not gpu_spoke and voice["kind"] == "stock" and not (sent or held):
            self._stock_failed(lang)
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
        if self._warm and held:
            copied = gpu_spoke or voice["kind"] == "clone"
            if not (copied and sent):   # a copied line whose start has gone out already is left as it is
                held = self._soften(lang, held, sr, copied, timings)
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
        self.sess.bus.broadcast({"type": "stats", **self.stats()})

    # ---------- v1.1 dense speech (app/v1/dense.py) ----------
    def _note_share(self, chunk: Chunk) -> None:
        """The speaking share of the last 30 s, noted with every phrase; over 70% the controller's dense mode."""
        assert self._share is not None
        self._share.add(chunk.t_speech_ms, chunk.t_speech_end_ms)
        now = max(chunk.t_speech_end_ms, self._last_end)
        share = self._share.share(now)
        was, self._dense = self._dense, bool(self.s.v1_live_ratectrl and self._share.dense(now))
        timings = self._pending[chunk.seq]["timings"]
        if share is not None:
            timings["share"] = round(100 * share)
        if self._dense:
            timings["dense"] = 1
        if was != self._dense and self._trace:
            trace.event("live_dense", session=self.sess.id, seq=chunk.seq, on=self._dense,
                        share=round(100 * share) if share is not None else None)

    def _controller(self, lang: str) -> dense.RateController:
        if lang not in self._ctl:
            self._ctl[lang] = dense.RateController(self.s.v1_ratectrl_kp, self.s.v1_ratectrl_ki,
                                                   self.s.v1_ratectrl_setpoint_ms / 1000, self.s.v1_ratectrl_relax_s,
                                                   self.s.v1_ratectrl_min_scale)
        return self._ctl[lang]

    def _voice_kind(self, lang: str) -> str:
        """The kind of voice this language's next line is expected in (the expansion model keeps them apart)."""
        if self._gpu_speaks(lang) or self._gpu_planned(lang):
            return "gpu"
        return "clone" if self.voice is not None and lang in self.clone_langs else "stock"

    def _budget_plan(self, lang: str, chunk: Chunk, behind: int) -> dict[str, Any] | None:
        """`V1_LIVE_BUDGET`: this phrase's slot as a length for the translator, or None when nothing is known
        yet of this voice in this language (then v0's word limit applies).

        The slot is the phrase's own span. The scale comes from the controller (`V1_LIVE_RATECTRL`, at most
        `v1_dense_scale` in dense mode); without it, from how far behind the dub is, in two steps."""
        if self._xp is None:
            return None
        n_src = len(chunk.text.split())
        slot = chunk.t_speech_end_ms - chunk.t_speech_ms
        if not PACE_MS[0] * n_src <= slot <= PACE_MS[1] * n_src:   # a span that is not believed: the speaker's pace
            slot = int(n_src * self._src_ms_per_word)
        if self.s.v1_live_ratectrl:
            scale = self._controller(lang).scale
            if self._dense:
                scale = min(scale, self.s.v1_dense_scale)
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
        return plan

    async def _within_budget(self, lang: str, chunk: Chunk, text: str, plan: dict[str, Any]) -> str:
        """`V1_LIVE_BUDGET`: the translation's expected duration against its slot. More than `v1_budget_over`
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

    def dense_stats(self) -> dict[str, Any]:
        """For the session's metrics: dense mode, each language's controller, the expansion model as it stands."""
        out: dict[str, Any] = {}
        if self.s.v1_live_ratectrl:
            out["dense"] = self._dense
            out["ratectrl"] = {lg: {"scale": round(c.scale, 2), "integral": round(c.integral, 2),
                                    "backlog_s": round(c.backlog_s, 2)} for lg, c in self._ctl.items()}
        if self._xp is not None:
            out["expansion"] = self._xp.state()
        return out

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
