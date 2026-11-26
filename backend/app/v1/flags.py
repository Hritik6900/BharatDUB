"""What is in force, for `/api/v1/flags`: a read-only diagnostic for us (no page for users lists it).

Since v1.2 nothing is decided here: `app/v1/mode.py` is the one place. The `V1_*` keys are kept because the
website's own code asks for two of them (is a recording possible, is HQ on offer) and scripts read the rest.
"""
from typing import Any

from app.config import Settings, get_settings
from app.v1 import mode as v1mode

# Features that have (or had) a setting of their own, under the name they are reported by.
FLAGS = ("v1_trace", "v1_router", "v1_tts_server", "v1_tts_maya", "v1_live_stock_default", "v1_live_late_shorten",
         "v1_live_backcheck", "v1_studio_hq", "v1_fit_115", "v1_api_log", "v1_breaker", "v1_live_degrade",
         "v1_live_budget", "v1_en_single_voice", "v1_hq_judge", "v1_hq_calibrate", "v1_hq_adaptive", "v1_hq_normalise",
         "v1_hq_auto_glossary", "v1_hq_review", "v1_live_record", "v1_listen_test")


def flags(settings: Settings | None = None) -> dict[str, Any]:
    s = settings or get_settings()
    st = v1mode.state(s)
    return {**{name.upper(): v1mode.on(name.removeprefix("v1_"), s) for name in FLAGS}, "V1_STORE": s.v1_store,
            "V1_MODE": st["mode"], "overrides": st["overrides"],
            "auto": {name: st["features"][name] for name in v1mode.NEW}}


def on(name: str) -> bool:
    """`name` with or without its `v1_` prefix."""
    return v1mode.on(name.removeprefix("v1_"))
