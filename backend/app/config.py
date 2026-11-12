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

    supabase_url: str = ""
    supabase_service_key: SecretStr = SecretStr("")

    upload_ttl_hours: int = 24
    max_video_seconds: int = 180
    cors_origins: str = "http://localhost:3000"

    tts_model: str = "timbre-v2.5"
    tts_sample_rate: int = 44100

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
