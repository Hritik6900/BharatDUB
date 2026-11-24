"""Studio HQ: the heard-back judge (`V1_HQ_JUDGE`).

A dubbed line is heard back by a speech-to-text and the share of its words that came back is its score. Which
speech-to-text hears a language best is a table, not one fixed provider:

  * the order is `v1_hq_judge_order` (shipped: the hosted service first, then our GPU Whisper, then the QA
    server's Whisper), and a single language can have its own order in `v1_hq_judge_by_lang`;
  * a judge that does not hear a language is left out for it (our GPU model on :9030 is a Hindi and Hinglish
    model: a judge for Hindi lines only; the QA server's multilingual Whisper on :9045 hears every language but
    is not running until `NEEDS_APPROVAL.md` item 6);
  * when a judge fails or does not answer in time the next one hears the line, and the result says who judged
    (`by`) and who was passed over (`passed_over`), so two scores are only ever compared when the same judge gave
    both.

The comparison itself is corrected too (`qa.HEARD_RULE_NFC`): both texts are brought to one spelling of every
letter before words are compared, because the same Bengali or Hindi letter can be stored in two ways and the
first HQ jobs lost points for lines that were heard back word for word.

With the flag off `Stages.score` is what it was: the `score` list of the routing file.
"""
from pathlib import Path
from typing import Any

from app.config import Settings
from app.providers.base import ProviderError
from app.v1.qa import HEARD_RULE_NFC, heard_share

JUDGES = ("prisma", "whisper_gpu", "qa_server")
WHISPER_HEARS = {"hi-IN"}      # our GPU model writes Hindi and Hinglish, in Latin letters


def hears(name: str, lang: str) -> bool:
    return name in ("prisma", "qa_server") or (name == "whisper_gpu" and lang in WHISPER_HEARS)


def order(s: Settings, lang: str) -> list[str]:
    """The judges for a language as configured, best first (unknown names are dropped)."""
    names = [n.strip() for n in (s.v1_hq_judge_order or "").split(",")]
    for pair in (s.v1_hq_judge_by_lang or "").split(";"):
        key, _, val = pair.partition("=")
        if key.strip() == lang and val.strip():
            names = [n.strip() for n in val.split(",")]
    return [n for n in dict.fromkeys(names) if n in JUDGES and hears(n, lang)]


def chain(st: Any, lang: str) -> list[str]:
    """The judges that can hear this language and are configured on this backend."""
    return [n for n in order(st.r.s, lang) if st.r.available(n)]


async def _hear(st: Any, name: str, wav: Path, lang: str) -> str:
    if name == "qa_server":
        from app.v1.qa import QAClient
        return str((await QAClient(st.r.s).score(wav, "", lang)).get("heard") or "")
    stt = st.r.provider("stt", name)
    text = str((await stt.transcribe(str(wav), lang)).text or "")
    if name == "whisper_gpu" and text.strip():
        # Our model writes Hindi in Latin letters; the line it is compared with is in Devanagari.
        from app.providers import _local_llm
        from app.providers.llm_local import has_latin
        text = await _local_llm().to_devanagari(text)
        if has_latin(text):
            raise ProviderError("whisper_gpu: its Latin transcript could not be written in Devanagari")
    return text


async def score(st: Any, wav: Path, text: str, lang: str, ref_wav: Path | None = None) -> dict[str, Any]:
    """`Stages.score` with the flag on: {heard, backcheck, similarity, by, rule, passed_over}."""
    names = chain(st, lang)
    start = len(st.fallbacks)

    async def call(name: str) -> dict[str, Any]:
        heard = await _hear(st, name, wav, lang)
        return {"heard": heard, "backcheck": round(heard_share(text, heard, HEARD_RULE_NFC), 3), "similarity": None,
                "by": name, "rule": HEARD_RULE_NFC}
    got: dict[str, Any] = await st._run("score", names, call)
    got["passed_over"] = [f["provider"] for f in st.fallbacks[start:] if f.get("stage") == "score"]
    if ref_wav is not None and st.r.available("qa_server"):
        # The words are the judge's; how close the voice is to the speaker's is still the QA server's to say.
        try:
            from app.v1.qa import QAClient
            got["similarity"] = (await QAClient(st.r.s).score(wav, text, lang, ref_wav)).get("similarity")
        except ProviderError:
            pass
    return got
