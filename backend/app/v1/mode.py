"""v1.2: the one place that says whether a feature is in force (`on`), and with which pinned value (`pin`).

`V1_MODE` has two values:

  auto     (the default) the mode decides. Nobody manages switches: what is listed in `AUTO` below is on or off
           as written there, the per-feature `V1_*` names in the env file are not read, and the only way to
           change one behaviour is an entry in `backend/config/overrides.yaml` (an emergency off-switch or a
           pinned value; the file ships with every entry commented out).
  manual   every feature follows its own `V1_*` setting, as before v1.2. For measurements (a baseline beside
           auto), the comparison backends and the test suite. What v1.2 added (`NEW`) is off there.

Rules that hold in both modes are written here and nowhere else: Studio HQ never runs without the review.

The overrides file is read once, when it is first asked for (`reload()` reads it again). A file that is missing
is no overrides; a file that cannot be read, is not a mapping, or holds an unknown name or value is logged and
that part is ignored: a bad file never stops the backend.
"""
import logging
from pathlib import Path
from typing import Any

from app.config import BACKEND_DIR, Settings, get_settings

log = logging.getLogger("bharatdub.mode")
OVERRIDES_FILE = BACKEND_DIR / "config" / "overrides.yaml"

# What auto mode does. True = always on, False = not part of auto (an override may pin it on for a trial).
AUTO: dict[str, bool] = {
    # always on, as decided (v1.2 Part 2)
    "trace": True, "router": True, "api_log": True, "breaker": True, "live_degrade": True,
    "live_stock_default": True, "studio_hq": True, "hq_review": True, "fit_115": True, "hq_adaptive": True,
    "hq_normalise": True, "hq_auto_glossary": True,
    # on because the reports recommend it with HQ (the counting rule that no longer takes points off Bengali)
    "hq_judge": True,
    # the Live budget exists in auto; `auto_budget` makes it apply only while the dub is behind or speech is dense
    "live_budget": True, "auto_budget": True, "meaning_check": True,
    # English in one voice, chosen once at the session's start from a measurement
    "en_single_voice": True, "en_auto": True,
    # a refused line is spoken by another voice; guards on every line
    "voice_fallback": True, "script_guard": True, "shift_check": True,
    # needs the session's own ask (consent); pages that only add a tool for us
    "live_record": True, "hq_calibrate": True, "listen_test": True,
    # not part of auto: never measured alone, or their server is not deployed
    "tts_server": False, "tts_maya": False, "live_late_shorten": False, "live_backcheck": False,
}
# Added by v1.2: there is no `V1_*` setting for them, and in manual mode they are off (manual = as before v1.2).
NEW = ("auto_budget", "meaning_check", "en_auto", "voice_fallback", "script_guard", "shift_check")
# Values an override may pin. `en_voice`: the one English voice of a session without measuring.
PINS: dict[str, tuple[str, ...]] = {"en_voice": ("stock", "copy")}

_TRUE, _FALSE = ("on", "true", "yes", "1"), ("off", "false", "no", "0")
_cache: dict[str, Any] | None = None
_cache_path: str | None = None


def _path(s: Settings) -> Path:
    own = getattr(s, "v1_overrides_file", "")
    return Path(own) if own else OVERRIDES_FILE


def load(path: Path) -> dict[str, Any]:
    """{feature: bool, pin: value} from the file; {} when it is missing. Never raises."""
    try:
        if not path.exists():
            return {}
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))   # a file saved with a byte-order mark (PowerShell) reads the same
    except Exception as e:  # noqa: BLE001 - a bad file must not stop the backend
        log.error("overrides: %s cannot be read (%s); no override is in force", path, str(e)[:160])
        return {}
    if data is None:
        return {}
    if not isinstance(data, dict):
        log.error("overrides: %s is not a list of `name: value` lines; no override is in force", path)
        return {}
    out: dict[str, Any] = {}
    for key, val in data.items():
        name = str(key).strip().lower().removeprefix("v1_")
        word = str(val).strip().lower() if not isinstance(val, bool) else ("on" if val else "off")
        if name in AUTO and word in _TRUE + _FALSE:
            out[name] = word in _TRUE
        elif name in PINS and word in PINS[name]:
            out[name] = word
        else:
            log.error("overrides: `%s: %s` is not known and is ignored", key, val)
    if out:
        log.warning("overrides in force: %s", ", ".join(f"{k}={v}" for k, v in sorted(out.items())))
    return out


def overrides(settings: Settings | None = None) -> dict[str, Any]:
    """The overrides in force: those of the file, in auto mode; none in manual mode."""
    global _cache, _cache_path
    s = settings or get_settings()
    if not is_auto(s):
        return {}
    path = _path(s)
    if _cache is None or _cache_path != str(path):
        _cache, _cache_path = load(path), str(path)
    return _cache


def reload() -> None:
    global _cache
    _cache = None


def is_auto(settings: Settings | None = None) -> bool:
    # a stand-in settings object without the field (tests) is read as before v1.2: by its own attributes
    return str(getattr(settings or get_settings(), "v1_mode", "manual")).strip().lower() != "manual"


def on(feature: str, settings: Settings | None = None) -> bool:
    """Is `feature` in force? The single answer for the whole backend."""
    s = settings or get_settings()
    if feature not in AUTO:
        raise KeyError(f"unknown feature: {feature}")
    if feature == "hq_review":   # HQ on means the review is on, in every mode, whatever anything else says
        if on("studio_hq", s):
            return True
    if not is_auto(s):
        return False if feature in NEW else bool(getattr(s, f"v1_{feature}"))
    ov = overrides(s)
    if feature in ov:
        return bool(ov[feature])
    return AUTO[feature]


def pin(name: str, settings: Settings | None = None) -> str | None:
    """A value pinned in the overrides file (auto mode), or None."""
    got = overrides(settings).get(name)
    return str(got) if name in PINS and got is not None else None


def state(settings: Settings | None = None) -> dict[str, Any]:
    """For `/api/v1/flags` (a diagnostic for us, not shown on a page for users)."""
    s = settings or get_settings()
    return {"mode": "auto" if is_auto(s) else "manual", "overrides": dict(overrides(s)),
            "features": {name: on(name, s) for name in AUTO}}
