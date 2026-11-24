"""Client for the QA server (gpu_engine_v1/qa_server.py, :9045): hears a dubbed line back, compares its voice
with the speaker's, and tells speakers apart.

  POST /score    multipart audio, text, lang, [ref]  -> {heard, backcheck, similarity}
  POST /diarize  multipart audio                     -> {segments: [{start, end, speaker}]}
"""
import unicodedata
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.providers.base import ProviderError


HEARD_RULE = "spaces-aside-1"   # which rule a stored score was worked out with (see heard_share)
HEARD_RULE_NFC = "nfc-2"        # the same rule on normalised letters (`V1_HQ_JUDGE`)


def _words(text: str, nfc: bool = False) -> list[str]:
    if nfc:
        # One letter can be stored two ways: Bengali য় ড় ঢ় and the Devanagari nukta letters exist as one code
        # point and as letter + dot. A translation model writes one, a speech-to-text the other, and the two
        # look and sound the same. Seen on the first HQ jobs: a Bengali line heard back word for word scored 86%,
        # and every take of it scored the same. Normalising both sides makes them one spelling. Joiners that
        # cannot be seen are dropped instead of splitting the word.
        text = unicodedata.normalize("NFC", text)
        text = "".join(c for c in text if unicodedata.category(c) != "Cf")
    kept = "".join(c if unicodedata.category(c)[0] in "LMN" else " " for c in text.lower())
    return kept.split()


def rule_now(settings: Settings | None = None) -> str:
    return HEARD_RULE_NFC if (settings or get_settings()).v1_hq_judge else HEARD_RULE


def heard_share(said: str, heard: str, rule: str = HEARD_RULE) -> float:
    """Share of the words in `said` that a listener got (0-1).

    A word counts when it was heard as a word (the same word, or one with the same first four letters), or when
    its letters are there in what was heard with the spaces set aside. The second rule is for spelling, not for
    hearing: a dub says "pi si aar" as three words and the speech-to-text writes "PCR" as one, or splits a long
    compound in two; the first rule alone counted those lines as half lost (seen on the first HQ run: the same
    low score on every take of such a line). `rule` = HEARD_RULE_NFC compares normalised letters (see `_words`).
    """
    nfc = rule == HEARD_RULE_NFC
    want, got = _words(said, nfc), _words(heard, nfc)
    if not want:
        return 0.0
    have = set(got)
    run = "".join(got)
    hit = 0
    for w in want:
        if w in have or any(w[:4] == g[:4] for g in have) or (len(w) >= 2 and w in run):
            hit += 1
    return hit / len(want)


class QAClient:
    name = "qa_server"

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None) -> None:
        self.s = settings or get_settings()
        self.url = self.s.v1_qa_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=3.0))

    async def score(self, wav: Path, text: str, lang: str, ref_wav: Path | None = None) -> dict[str, Any]:
        files: dict[str, Any] = {"audio": (wav.name, wav.read_bytes(), "audio/wav")}
        if ref_wav is not None and ref_wav.exists():
            files["ref"] = (ref_wav.name, ref_wav.read_bytes(), "audio/wav")
        try:
            r = await self._client.post(self.url + "/score", data={"text": text, "lang": lang}, files=files)
            r.raise_for_status()
            j = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise ProviderError(f"qa.score: {e}") from e
        heard = j.get("heard") or ""
        return {"heard": heard, "backcheck": round(heard_share(text, heard), 3), "similarity": j.get("similarity"),
                "rule": HEARD_RULE}

    async def diarize(self, wav: Path) -> list[dict[str, Any]]:
        try:
            r = await self._client.post(self.url + "/diarize",
                                        files={"audio": (wav.name, wav.read_bytes(), "audio/wav")})
            r.raise_for_status()
            return list(r.json().get("segments") or [])
        except (httpx.HTTPError, ValueError) as e:
            raise ProviderError(f"qa.diarize: {e}") from e
