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
    def llm_fast(self) -> str:
        return self.llm_model_fast or self.llm_model


@lru_cache
def get_settings() -> Settings:
    return Settings()
