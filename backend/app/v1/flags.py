"""The v1 flags in one place. Values come from the settings (v1's own backend/.env); all default to off."""
from typing import Any

from app.config import Settings, get_settings

FLAGS = ("v1_trace", "v1_router", "v1_phrase_dynamic", "v1_spec_translate", "v1_tts_server", "v1_tts_maya",
         "v1_live_stock_default", "v1_live_late_shorten", "v1_live_backcheck", "v1_llm_prefix_cache", "v1_studio_hq",
         "v1_fit_115", "v1_api_log", "v1_breaker", "v1_live_degrade")


def flags(settings: Settings | None = None) -> dict[str, Any]:
    s = settings or get_settings()
    return {**{name.upper(): bool(getattr(s, name)) for name in FLAGS}, "V1_STORE": s.v1_store}


def on(name: str) -> bool:
    return bool(getattr(get_settings(), name))
