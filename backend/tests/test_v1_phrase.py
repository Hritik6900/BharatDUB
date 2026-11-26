"""v1 Live phrase logic: short lines joined to the next (the dynamic phrase sizes went in v1.2)."""
import asyncio

import pytest

from app.config import get_settings
from app.live.assembler import Chunk, Phraser
from app.live.pipeline import LivePipeline
from app.live.session import LiveSession
from app.providers.base import TranscriptEvent
from app.providers.mock import MockTTS
from app.v1.phrase import ShortLineMerger, n_words, same_words

def chunk(seq: int, text: str, start: int = 0, end: int = 0) -> Chunk:
    return Chunk(seq, text, start, end or start + 500, end or start + 600)


def test_short_line_waits_and_joins_the_next_line():
    m = ShortLineMerger(under_words=3, wait_ms=1500)
    assert m.push(chunk(1, "Kaise?", 1000), now_ms=1100) == []          # held
    assert m.poll(2000) is None                                          # still waiting
    out = m.push(chunk(2, "aaj hum naya game khelenge", 2200, 4000), now_ms=4100)
    assert len(out) == 1 and out[0].text == "Kaise? aaj hum naya game khelenge"
    assert out[0].seq == 2 and out[0].t_speech_ms == 1000 and out[0].t_speech_end_ms == 4000
    assert m.merged == 1 and m.held is None


def test_short_line_goes_out_alone_when_nothing_follows():
    m = ShortLineMerger(under_words=3, wait_ms=1500)
    m.push(chunk(1, "Batao.", 0), now_ms=100)
    assert m.poll(1500) is None
    alone = m.poll(1600)
    assert alone is not None and alone.text == "Batao." and m.alone == 1
    assert m.poll(5000) is None


def test_long_lines_pass_straight_through_and_two_short_ones_join():
    m = ShortLineMerger(under_words=3)
    assert [c.text for c in m.push(chunk(1, "ye teen shabd"), 0)] == ["ye teen shabd"]
    assert m.push(chunk(2, "haan"), 0) == []
    out = m.push(chunk(3, "theek hai"), 10)                              # joined: never held a second time
    assert [c.text for c in out] == ["haan theek hai"]
    assert n_words("hai? ...") == 1


def test_same_words_ignores_case_and_punctuation():
    assert same_words("Aaj hum khelenge.", "aaj hum khelenge")
    assert not same_words("aaj hum khelenge", "aaj hum nahi khelenge")


# ---------- in the pipeline ----------
class CountingLLM:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    async def translate_chunk(self, text, target, glossary, context, **kw):
        self.calls.append((target, text))
        await asyncio.sleep(0.01)
        return f"{target}:{text}"

    async def shorten(self, text, target, max_seconds, max_words=None):
        return " ".join(text.split()[:max_words or 3])


class NoSTT:
    async def stream(self, frames, lang, **kw):
        async for _ in frames:
            if False:
                yield None


def pipeline(monkeypatch, **flags) -> tuple[LivePipeline, CountingLLM, asyncio.Queue]:
    s = get_settings()
    for k, v in flags.items():
        monkeypatch.setattr(s, k, v)
    sess = LiveSession({"id": "v1s", "target_langs": ["ta-IN"], "src_lang": "hi-IN"})
    llm = CountingLLM()
    p = LivePipeline(sess, stt=NoSTT(), llm=llm, tts=MockTTS())
    p.running = True
    return p, llm, sess.bus.subscribe("ta-IN")


async def captions(q: asyncio.Queue, wait: float = 0.1) -> list[str]:
    await asyncio.sleep(wait)
    out = []
    while not q.empty():
        m = q.get_nowait()
        if m.get("type") == "caption":
            out.append(m["text"])
    return out


async def test_late_line_is_shortened_not_skipped(monkeypatch):
    p, llm, q = pipeline(monkeypatch, v1_live_late_shorten=True)
    text = "ஒன்று இரண்டு மூன்று நான்கு ஐந்து ஆறு ஏழு எட்டு ஒன்பது பத்து"
    assert await p._shorter("ta-IN", text, late_by=5000, limit=4000) == "ஒன்று இரண்டு மூன்று நான்கு"
    assert await p._shorter("ta-IN", text, late_by=9000, limit=4000) is None    # far too late: skipped as before
    assert await p._shorter("ta-IN", "மூன்று சொற்கள் மட்டும்", late_by=5000, limit=4000) is None   # nothing to shorten


def test_stock_default_and_session_glossary(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.db import LocalStore
    from app.main import app
    store = LocalStore(tmp_path / "db.json")
    monkeypatch.setattr("app.live.routes.get_store", lambda: store)
    monkeypatch.setattr("app.live.session.get_store", lambda: store)
    s = get_settings()
    c = TestClient(app)
    body = {"target_langs": ["ta-IN"], "voice_from_stream": True, "voice_consent": True, "glossary": ["Valorant", " ", "Ace"]}
    r = c.post("/api/live/sessions", json=body)
    assert r.status_code == 201 and r.json()["voice_from_stream"] is True       # flag off: as v0
    row = store._db["live_sessions"][-1]
    assert row["glossary"] == ["Valorant", "Ace"]
    monkeypatch.setattr(s, "v1_live_stock_default", True)
    r = c.post("/api/live/sessions", json=body)
    assert r.status_code == 201 and r.json()["voice_from_stream"] is False      # no streamer profile: stock voices
    assert c.post("/api/live/sessions", json={"target_langs": ["ta-IN"], "voice_from_stream": True}).status_code == 201




async def test_pipeline_in_manual_mode_never_joins_a_short_line(monkeypatch):
    """Joining short lines belongs to dense speech in auto mode; in manual mode there is no merger at all."""
    p, llm, q = pipeline(monkeypatch)
    assert p._merger is None and type(p.phraser) is Phraser
    p._on_stt(TranscriptEvent(kind="final", text="Kaise?", utterance_id="a", audio_duration_ms=400))
    assert await captions(q) == ["ta-IN:Kaise?"]


REMOVED = ("v1_spec_translate", "v1_spec_stable_ms", "v1_llm_prefix_cache", "v1_phrase_dynamic", "v1_live_ratectrl",
           "v1_live_native_speed", "v1_live_warmstart", "v1_first_phrase_min_words", "v1_first_phrase_max_words",
           "v1_phrase_min_words", "v1_phrase_max_words", "v1_merge_under_words", "v1_native_max", "v1_native_floor_ms",
           "v1_warm_fade_ms", "v1_warm_level_lines")


@pytest.mark.parametrize("v1_mode", ["manual", "auto"])
def test_removed_flags_are_gone_and_an_env_file_that_still_sets_them_is_read(tmp_path, monkeypatch, v1_mode):
    """v1.1 WS6 took V1_SPEC_TRANSLATE and V1_LLM_PREFIX_CACHE out, v1.2 took V1_PHRASE_DYNAMIC, V1_LIVE_RATECTRL,
    V1_LIVE_NATIVE_SPEED and V1_LIVE_WARMSTART. An env file written before that must still load, in either mode,
    and the old names switch nothing on."""
    from app.config import Settings
    from app.v1.flags import FLAGS, flags
    monkeypatch.setenv("V1_MODE", v1_mode)
    env = tmp_path / ".env"
    env.write_text("\n".join([f"{name.upper()}=true" if "words" not in name and "_ms" not in name and "max" not in name
                              else f"{name.upper()}=7" for name in REMOVED] + [""]))
    s = Settings(_env_file=env)
    assert s.v1_mode == v1_mode
    for name in REMOVED:
        assert not hasattr(s, name) and name not in FLAGS and name.upper() not in flags(s)
    base = Settings(_env_file=None)
    assert flags(s) == flags(base)                                        # exactly what it is without those lines
    if v1_mode == "manual":
        assert not any(v for k, v in flags(s).items() if k.startswith("V1_") and k not in ("V1_STORE", "V1_MODE", "V1_HQ_ADAPTIVE"))
