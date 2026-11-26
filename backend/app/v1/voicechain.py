"""v1.2: who speaks a line when the voice that was asked refuses, fails or makes nothing. The order is written
here and nowhere else; Live and Studio both ask this file.

  gpu         the speaker's copied voice on our own engine
  copy        the hosted copy of the speaker's voice
  stock       the language's usual stock voice
  stock_alt   the language's other stock voice (where it has two); the same hosted service, another voice

A line starts with the voice its session or job chose. When that makes nothing, the others are asked in the
order of `ORDER`, each once, leaving out those the line cannot have (no copied voice, an engine that does not
speak the language, a language with one stock voice). Only when every one of them made nothing is the line
marked as unspoken, with what each of them answered.

A hosted stock voice that refuses is asked once more first (`RETRY_SAME`): on 25 Nov 2026 it refused lines within
0.2 s with HTTP 502 and a second ask brought 29% of them back.
"""
from app.config import VOICE_BY_LANG, VOICE_BY_LANG_MALE
from app.providers.base import VoiceSpec

ORDER = ("gpu", "copy", "stock", "stock_alt")
RETRY_SAME = ("stock",)
LATER_TIMEOUT_S = 8.0      # a voice asked after the first one gets this long


def rest(tried: list[str], available: set[str]) -> list[str]:
    """The voices still to ask, in order: those of `ORDER` that the line can have and that were not asked yet."""
    return [k for k in ORDER if k in available and k not in tried]


def stock(lang: str) -> VoiceSpec:
    return {"kind": "stock", "voice": VOICE_BY_LANG.get(lang, VOICE_BY_LANG["hi-IN"])}


def stock_alt(lang: str) -> VoiceSpec | None:
    """The language's other stock voice, or None when it has only one."""
    name = VOICE_BY_LANG_MALE.get(lang)
    return {"kind": "stock", "voice": name} if name and name != VOICE_BY_LANG.get(lang) else None
