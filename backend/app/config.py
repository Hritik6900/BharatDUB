"""App settings, loaded from env / backend/.env. Never log secret values."""
from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent

LANG_NAMES: dict[str, str] = {
    "hi-IN": "Hindi", "ta-IN": "Tamil", "te-IN": "Telugu", "bn-IN": "Bengali",
    "mr-IN": "Marathi", "kn-IN": "Kannada", "ml-IN": "Malayalam", "gu-IN": "Gujarati",
    "pa-IN": "Punjabi", "en-IN": "English",
}

# Timbre v2.5 voices, each used in its preferred language (docs.gnani.ai Voice Catalog, 2026-11-13).
VOICE_BY_LANG: dict[str, str] = {
    "hi-IN": "Nalini", "ta-IN": "Asmita", "bn-IN": "Kirra", "te-IN": "Suhana",
    "en-IN": "Kaveri", "kn-IN": "Saanvi", "ml-IN": "Reshma", "mr-IN": "Zahira",
    "gu-IN": "Falak", "pa-IN": "Mehuli",
}
VOICE_BY_LANG_MALE: dict[str, str] = {
    "hi-IN": "Deepak", "bn-IN": "Dhruva", "en-IN": "Pranav", "kn-IN": "Kavin",
    "ml-IN": "Riyaan", "mr-IN": "Ishaan", "gu-IN": "Veera", "pa-IN": "Zayan",
}

DEFAULT_GLOSSARY = ["bro", "subscribe", "like", "share", "reel", "vlog", "OK", "clutch", "GG"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    gnani_api_key: SecretStr = SecretStr("")
    gnani_base: str = "https://api.vachana.ai"
    gnani_max_concurrency: int = 1

    llm_base_url: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = ""
    llm_model_fast: str = ""
    # Optional `reasoning_effort` for reasoning models (e.g. "none" on Gemini Flash). Left unset, hidden
    # thinking can eat the max_tokens budget and truncate short translations.
    llm_reasoning_effort: str = ""
    llm_reasoning_effort_fast: str = ""   # for LLM_MODEL_FAST when it needs another value (flash-lite: `minimal`)

    supabase_url: str = ""
    supabase_service_key: SecretStr = SecretStr("")

    upload_ttl_hours: int = 24
    max_video_seconds: int = 180
    cors_origins: str = "http://localhost:3000"

    # Prisma output format. `codemix` keeps English words in Latin letters (game, chat, map), which is how
    # creators write and what the glossary matches; `verbatim` transliterates them into Devanagari.
    stt_format: str = "codemix"
    tts_model: str = "timbre-v2.5"
    tts_sample_rate: int = 44100

    studio_translate_ahead: bool = True  # translate all target languages at once instead of one by one
    live_sample_rate: int = 24000      # Live TTS PCM rate sent to viewers
    live_clone_max_lag_ms: int = 5000  # a Live chunk already this late is spoken in the stock voice (catch-up)
    live_clone_langs: int = 0          # languages (in session order) dubbed in the cloned voice; 0 = GNANI_MAX_CONCURRENCY
    live_partials: bool = True         # cut dub chunks from Prisma partials instead of waiting for the utterance to end
    live_partial_interval_ms: int = 300  # how often Prisma sends a partial (its default is 450)
    live_phrase_min_words: int = 6     # a phrase is cut at a clause boundary once it has this many settled words
    live_phrase_max_words: int = 12    # ... and at this many words with or without a boundary
    live_tts_only_heard: bool = True   # no TTS for a language nobody is tuned to (captions still go out)
    live_skip_after_ms: int = 8000     # a line already this late is not spoken at all (caption only)
    live_merge_max: int = 3            # phrases waiting behind the voice are spoken in one call, up to this many (1 = off)
    live_trim_silence: bool = True     # cut the silence Timbre puts before and after every phrase
    live_fit: bool = True              # when dubbed audio is piling up for viewers, shorten the next phrase (tempo, pitch kept)
    live_fit_after_ms: int = 600       # ... once more than this much audio is still waiting to be played
    live_fit_max_tempo: float = 1.3    # ... by at most this factor
    live_tts_speed: float = 1.15       # stock voices speak a little faster in Live so the dub keeps pace
    # Our own GPU voice engine for Live (IndicF5, not a Gnani model): the speaker's copied voice without Gnani's
    # one-request limit. Empty = off. See providers/tts_gpu.py.
    gpu_voice_url: str = ""
    gpu_voice_timeout_s: float = 6.0
    # Two engines, chosen per Live session and per Studio job (the "engine" button on the site):
    #   cloud  the hosted services, as before
    #   gpu    speech-to-text and translation on our own GPU machine too (gpu_engine/stt_engine.py and a vLLM
    #          server), the hosted services only as the fallback
    # The GPU engine is on offer when both URLs below are set. `ai_mode` is only what a caller gets when it does
    # not say which one it wants; left at `cloud`, nothing changes for a session that does not pick the GPU engine.
    ai_mode: str = "cloud"
    gpu_stt_url: str = ""              # e.g. http://127.0.0.1:9030
    gpu_llm_url: str = ""              # OpenAI-compatible, e.g. http://127.0.0.1:9020/v1
    gpu_llm_model: str = "local"
    # Who hears the speech in the GPU engine: `hosted` (the hosted service first, our GPU model behind it) or `gpu`
    # (our GPU model first, the hosted one behind it: nothing hosted in the path of a phrase). See FallbackSTT.
    gpu_stt_first: str = "hosted"
    # The GPU engine's voice: `f5` (IndicF5, as in the hosted engine) or `mio` (Indic-Mio, gpu_engine/mio_engine.py;
    # needs `gpu_mio_url`). The hosted engine always uses IndicF5. See providers/tts_gpu_mio.py.
    gpu_voice_model: str = "f5"
    gpu_mio_url: str = ""              # e.g. http://127.0.0.1:9040
    gpu_mio_lanes: int = 3             # lines the one Indic-Mio engine is given at once
    # GPU engine only (providers/tts_gpu_guard.py): IndicF5 swallows short lines. A line of at most
    # `gpu_voice_short_words` words is asked for at `gpu_voice_short_speed` of the speed (more time for it), and a
    # line that still comes out far too short is made again slower. `gpu_voice_short_engine` = `mio` gives such
    # lines to Indic-Mio instead: clearer, but a second voice between the copied one (heard on a real stream).
    # `gpu_voice_guard` False = lines go to IndicF5 as they are.
    gpu_voice_guard: bool = True
    gpu_voice_short_words: int = 3
    gpu_voice_short_speed: float = 0.75
    gpu_voice_short_engine: str = "f5"
    gpu_separate_url: str = ""         # Studio: Demucs on our GPU machine (gpu_engine/sep_engine.py); empty = this PC's CPU
    gpu_voice_native_speedup: bool = False  # let the engine itself speak faster when a line must be shortened
    # How lines come back from the engine: `mp3` (a tenth of the bytes of `pcm`, 30 ms to make), `opus` (same size,
    # 144 ms to make on the GPU machine's CPU) or `pcm`.
    gpu_voice_format: str = "mp3"
    gpu_voice_speed: float = 1.0       # < 1 = slower speech; the engine copies the pace of the voice sample
    # A copied voice that is slow in a language is asked to speak faster, so it reaches this pace (0 = off), by at
    # most `gpu_voice_pace_max`. The engine copies the sample's pace, and Tamil words are long: two recorded voices
    # took 640-650 ms a word in Tamil and 350-360 in Punjabi. Measured 2026-11-21, 16 lines a cell, words heard back
    # by Prisma: Tamil at engine speed 1.0 / 1.25 / 1.5 = 84-85 / 83-85 / 82-84% (424-443 ms a word at 1.5), and the
    # same after the 1.3x squeeze. Punjabi pushed under 300 ms a word lost words in one voice (91 -> 85 -> 62%),
    # so the pace is the rule, not a fixed factor.
    # Whole sessions (recorded voice, dense reel, two runs each way): Tamil phrases starting within 1 s of their
    # moment 55-58% -> 65-75%, at the squeeze limit 41-42 -> 31-34 of about 63, words heard back 73-79% -> 73-74%,
    # and the translator's word limit for an 8-word phrase 3-4 -> 5 words. Punjabi was already fast and is not touched.
    gpu_voice_pace_ms: int = 450
    gpu_voice_pace_max: float = 1.5
    # GPU engine only, off: the pace asked of the copied voice follows the speaker (the speaker's own ms a word
    # times `gpu_voice_pace_follow`, never under `gpu_voice_pace_floor_ms`, never over `gpu_voice_pace_ms`).
    # Measured 2026-11-21, Streamer Mode, recorded voice, dense reel, off against 1.7: within 1 s of the moment
    # 61% -> 61%, words heard back 84 / 79% -> 82 / 80%. No gain: the reel's speaker (195 ms a word) is faster
    # than any pace the voice stays clear at.
    gpu_voice_pace_follow: float = 0.0
    gpu_voice_pace_floor_ms: int = 340
    # Denoising steps asked of the engine per line; 0 = the engine's own setting (12, `NFE` in start_live.sh).
    # Measured 2026-11-21 on one stored voice, 8 lines each in Punjabi, Gujarati and Tamil, words heard back by
    # Prisma: 12 steps 79 / 73 / 60%, 16 steps 80 / 89 / 80%, 32 steps 89 / 82 / 80%; a line took 0.15 s longer at 16
    # and 0.7 s longer at 32; how close the voice is to the speaker did not change.
    # Whole sessions, six loops of the dense reel, about 70 lines a language, 12 against 16 steps. Recorded voice:
    # Tamil 67 -> 73%, Punjabi 74 -> 82%, timing equal. Voice learned from the stream: Tamil 81 -> 77%,
    # Bengali 78 -> 79%, and phrases starting within 2 s of their moment 97 -> 93%. So 16 only for a recorded voice.
    gpu_voice_steps: int = 16          # a recorded voice (Streamer Mode and its preview)
    gpu_voice_steps_stream: int = 12   # a voice learned from the stream (Live)
    # True: only a streamer who recorded their own voice with consent gets a copied voice, and any other Live session
    # speaks in stock voices. False (the user's choice on 15 Nov 2026): /live may also copy the voice on the stream
    # that is playing, behind the consent tick box (403 without it).
    live_clone_needs_streamer: bool = False
    live_brief: bool = True            # while a language's dub is running behind, ask for a condensed translation
    live_length_budget: bool = True    # tell the translator how many words fit the time the speaker took
    live_brief_after_ms: int = 500     # ... once it is this far behind
    # Sync mode: when the console reports the time of the video it feeds from, every phrase is dubbed for the
    # moment it was spoken and viewers hold their video this far behind, so picture and dub play together.
    live_sync: bool = True
    live_sync_delay_ms: int = 6000        # how far behind viewers hold the video to begin with (stock voices)
    live_sync_delay_clone_ms: int = 8500  # ... when the session uses a copied voice (a cloned line takes 2-3.5 s)
    live_sync_adapt: bool = True          # grow the delay by what the dub really needs when phrases keep coming late
    live_sync_delay_max_ms: int = 15000   # ... up to this
    # ... by at most this much at a time. It was 3000: one long line that arrived late in two languages added 3 s
    # for the rest of a session. Measured 2026-11-21 with the hold fixed at 6 / 7.5 / 9 s: 91 / 90 / 90% of phrases
    # started within 1 s of their moment, so a longer hold only removes the rare worst cases.
    live_sync_grow_step_ms: int = 1000
    live_warmup: bool = True              # one tiny translation when a session starts, so the first phrase is not slow
    live_sync_slack_ms: int = 400         # a dubbed phrase may run this much longer than the speech before it is sped up
    live_sync_clone_spare_ms: int = 2000  # the copied voice is used when at least this long is left before the audio is needed
    live_sync_late_skip_ms: int = 4000    # a phrase that would start this long after its moment is not spoken
    # The moment a phrase was spoken at is an estimate. Without this, the tail of a line was counted back from its end
    # at the speaker's pace and often landed before the phrase before it had ended (10 of 36 phrases in one run),
    # so its dub was due while the earlier dub was still playing. On: a tail starts when its first word was
    # heard, and no phrase starts before the one before it ended.
    live_stamp_fix: bool = True
    # ---------- v1 (docs/v1/ARCHITECTURE.md) ----------
    # Every new behaviour is behind a flag, default off: with all of them off this code runs as v0 does.
    v1_trace: bool = False              # a trace record per Live phrase and Studio line (JSONL + Prometheus)
    v1_router: bool = False             # providers are handed out from config/routing.yaml instead of the fixed table
    v1_phrase_dynamic: bool = False     # first phrase 4-6 words, later ones 8-12, lines under 3 words join the next
    v1_spec_translate: bool = False     # translation starts when a partial has stood still, redone if the final differs
    v1_tts_server: bool = False         # copied voice from the one batching server (V1_TTS_SERVER_URL) instead of 9001-9003
    v1_tts_maya: bool = False           # Maya 2 as a second candidate voice in Studio HQ
    v1_live_stock_default: bool = False  # a Live session without a streamer profile speaks in stock voices
    v1_live_late_shorten: bool = False  # a line that is too late is said in a shorter version instead of skipped
    v1_live_backcheck: bool = False     # a dubbed live line is heard back in the background and made again if wrong
    v1_llm_prefix_cache: bool = False   # our translation model: fixed rules first (the server caches that prefix), temperature 0.1
    v1_studio_hq: bool = False          # the HQ Studio path can be asked for (quality=hq on a job)
    v1_fit_115: bool = False            # Studio speeds a line up by at most 1.15x (v0: 1.35x), then shortens
    v1_api_log: bool = False            # one record per outbound provider request (no bodies, no keys) under V1_LOG_DIR/api
    v1_breaker: bool = False            # circuit breakers on our GPU endpoints + the link-stall detector (app/v1/breaker.py)
    v1_live_degrade: bool = False       # Live steps down (copied voice, stock voice, captions only, original sound) and back up
    v1_live_budget: bool = False        # v1.1: the translator gets the phrase's slot as words and letters; an answer over it is shortened once
    v1_live_ratectrl: bool = False      # v1.1: a PI controller on the dub's backlog scales that budget; dense mode over 70% speaking share
    v1_live_native_speed: bool = False  # v1.1: our voice engine is asked to speak a long line faster itself (pace floor), the rest by tempo
    v1_live_warmstart: bool = False     # v1.1: a session's start: every language and engine warmed, a stock voice matched to the speaker's pitch until the copied voice is ready, a softened change
    v1_en_single_voice: bool = False    # v1.1: English in a GPU-engine session is spoken in one voice for the whole session (V1_EN_VOICE)
    v1_log_dir: str = ""                # empty = logs/ at the top of the repository
    v1_store: str = "json"              # json (as v0) | postgres
    postgres_dsn: SecretStr = SecretStr("")
    redis_url: str = ""                 # job queue and live state; empty = in this process
    v1_routing_file: str = ""           # empty = backend/config/routing.yaml
    # New model servers (gpu_engine_v1/). Empty = not there; the router then uses the next provider in its list.
    v1_tts_server_url: str = ""         # :9041 one IndicF5 with batching, same calls as 9001-9003
    v1_maya_url: str = ""               # :9042
    v1_transcribe_url: str = ""         # :9043 Indic Transcribe
    v1_big_llm_url: str = ""            # :9044 OpenAI-compatible
    v1_big_llm_model: str = "big"
    v1_qa_url: str = ""                 # :9045 back-check + speaker similarity (+ diarization)
    # Breakers (V1_BREAKER): a timeout, or `fails` failed calls within `window_s`, opens an endpoint's circuit for
    # `open_s`; then one call is let through. The two limits are the whole time one live call may take on our GPU
    # before the next provider is asked (a line's translation, a line's voice); other calls keep their own timeouts.
    v1_breaker_fails: int = 2
    v1_breaker_window_s: float = 10.0
    v1_breaker_open_s: float = 30.0
    v1_breaker_translate_timeout_s: float = 3.0
    v1_breaker_voice_timeout_s: float = 4.0
    v1_link_probe_every_s: float = 5.0      # the detector asks every GPU endpoint this often while a session is live
    v1_link_probe_timeout_s: float = 2.0
    # Ladder (V1_LIVE_DEGRADE): two failures in a row take a step down; while a step is down it is tried again
    # every `probe_ms`, and the first success steps back up.
    v1_degrade_fails: int = 2
    v1_degrade_probe_ms: int = 10000
    v1_degrade_voice_wait_s: float = 8.0    # a streamer's stored voice may hold a session's start up this long
    v1_gpu_stats_url: str = ""          # the GPU machine's own numbers for the status page; empty = V1_QA_URL + /gpu
    # v1.1 dense speech (app/v1/dense.py). Budget: the dub may take `share` times the phrase's own span; an answer
    # whose expected duration is more than `over` times that is asked for once more, shorter.
    v1_budget_share: float = 1.0
    v1_budget_over: float = 1.15
    v1_budget_reask_timeout_s: float = 2.5
    v1_budget_behind_scale: float = 0.85    # without the controller: the budget while the dub is behind ...
    v1_budget_far_scale: float = 0.65       # ... and while it is more than 2 s behind
    v1_ratectrl_kp: float = 0.15            # budget taken off per second of backlog
    v1_ratectrl_ki: float = 0.03            # ... and per second of backlog held for a second
    v1_ratectrl_setpoint_ms: int = 250      # a backlog this small is in step
    v1_ratectrl_min_scale: float = 0.6      # the budget never goes under this share of the slot
    v1_ratectrl_relax_s: float = 4.0        # in step again: the budget comes back with this time constant
    v1_dense_share: float = 0.70            # speaking share of the last `v1_dense_window_ms` over which speech is dense
    v1_dense_off_share: float = 0.60        # ... and under which it is no longer
    v1_dense_window_ms: int = 30000
    v1_dense_scale: float = 0.9             # dense mode: the budget is at most this share of the slot
    v1_dense_max_tempo: float = 1.4         # dense mode: a line may be sped up this far (else live_fit_max_tempo)
    v1_dense_merge_under_words: int = 3     # dense mode: a line shorter than this joins the next one
    v1_native_max: float = 1.2              # native speed: the engine is asked for at most this much faster speech
    v1_native_floor_ms: int = 320           # ... and never for speech under this many ms a word
    # v1.1 session start and the one English voice (app/v1/warm.py)
    v1_warm_fade_ms: int = 150              # warm start: fade at the end of the last stock lines and the start of the first copied one
    v1_warm_level_lines: int = 2            # ... and this many copied lines are brought towards the stock voice's level
    v1_en_voice: str = "auto"               # auto | copy | stock. auto = the measured choice, today stock (the copy was 13 points worse on time)
    v1_en_copy_lead_ms: int = 3500          # copy: a line waits for a copy that is still being made until this long before it is due
    # Live phrase sizes with V1_PHRASE_DYNAMIC.
    v1_first_phrase_min_words: int = 4
    v1_first_phrase_max_words: int = 6
    v1_phrase_min_words: int = 8
    v1_phrase_max_words: int = 12
    v1_merge_under_words: int = 3       # a line shorter than this waits for the next one
    v1_merge_wait_ms: int = 1500        # ... this long at most, then it goes out alone
    v1_spec_stable_ms: int = 300        # a partial unchanged for this long is translated ahead of its final
    v1_late_skip_factor: float = 2.0    # with late-shorten: skipped only when later than this times the limit
    v1_backcheck_min: float = 0.5       # live back-check: a line heard back under this share of words is made again
    # Studio HQ.
    v1_hq_nbest: int = 4                # voice versions of a line that failed its check (the first is always made)
    v1_hq_backcheck_min: float = 0.9    # share of words heard back for a version to pass
    v1_hq_similarity_min: float = 0.0   # speaker similarity to pass; 0 = measured and stored, not a gate
    v1_fit_max_speed: float = 1.15
    v1_hq_duck_db: float = -9.0         # sidechain ducking: how far the background goes down under speech
    v1_hq_loudness_lufs: float = -16.0  # 0 = no loudness normalisation
    # Cost per minute on the numbers page: nothing is shown for a rate that is 0 (not set).
    v1_gpu_rate_per_hour: float = 0.0   # the A100's price per hour, in the currency below
    v1_cost_currency: str = "USD"
    v1_stt_rate_per_min: float = 0.0    # hosted speech-to-text, per minute of audio
    v1_tts_rate_per_1k_chars: float = 0.0  # hosted voice, per 1000 characters
    v1_llm_rate_per_call: float = 0.0   # hosted translation, per call

    mock_providers: bool = False       # simulate Gnani + LLM for UI work without keys (UI shows a banner)

    data_dir: str = ""                 # local working files + cache; default backend/data
    studio_separate: bool = True       # run Demucs (stage 3)
    public_api_base: str = "http://localhost:8000"

    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir) if self.data_dir else BACKEND_DIR / "data"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def use_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_key.get_secret_value())

    @property
    def gnani_ws_base(self) -> str:
        return self.gnani_base.replace("https://", "wss://").replace("http://", "ws://")

    @property
    def gpu_mode_ready(self) -> bool:
        """The all-GPU engine can be chosen: its speech-to-text and translation servers are configured."""
        return bool(self.gpu_stt_url and self.gpu_llm_url)

    @property
    def llm_fast(self) -> str:
        return self.llm_model_fast or self.llm_model


@lru_cache
def get_settings() -> Settings:
    return Settings()
