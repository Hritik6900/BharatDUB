"""The v1 flags in one place. Values come from the settings (v1's own backend/.env). All default to off but
`V1_HQ_ADAPTIVE` (on since 26 Nov 2026; it acts on HQ jobs only)."""
from typing import Any

from app.config import Settings, get_settings

FLAGS = ("v1_trace", "v1_router", "v1_phrase_dynamic", "v1_tts_server", "v1_tts_maya",
         "v1_live_stock_default", "v1_live_late_shorten", "v1_live_backcheck", "v1_studio_hq",
         "v1_fit_115", "v1_api_log", "v1_breaker", "v1_live_degrade", "v1_live_budget", "v1_live_ratectrl",
         "v1_live_native_speed", "v1_live_warmstart", "v1_en_single_voice", "v1_hq_judge", "v1_hq_calibrate",
         "v1_hq_adaptive", "v1_hq_normalise", "v1_hq_auto_glossary", "v1_hq_review", "v1_live_record",
         "v1_listen_test")


def flags(settings: Settings | None = None) -> dict[str, Any]:
    s = settings or get_settings()
    out = {**{name.upper(): bool(getattr(s, name)) for name in FLAGS}, "V1_STORE": s.v1_store}
    # What is in force, not only what was written: Studio HQ never runs without the review (app/v1/hq/review.py).
    out["V1_HQ_REVIEW"] = bool(s.v1_hq_review or s.v1_studio_hq)
    return out


def on(name: str) -> bool:
    return bool(getattr(get_settings(), name))
