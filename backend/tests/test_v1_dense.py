"""v1.1 Live dense speech: dub length against its slot, the expansion model, the budget and its controller."""
import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

from app.config import get_settings
from app.db import LocalStore
from app.live.pipeline import LivePipeline
from app.live.session import LiveSession
from app.providers.mock import MockTTS
from app.v1 import dense, metrics, trace
from app.v1.dense import ExpansionModel, RateController, SpeakingShare

TA = "ta-IN"
WORD = "அஆஇஈஉஊ"                       # six letters
LINE10 = " ".join([WORD] * 10)          # 60 letters
LINE6 = " ".join([WORD] * 6)            # 36 letters
LINE7 = " ".join([WORD] * 7)
SEED = {"ta-IN|gpu": {"ms_per_char": 60.0, "ms_per_word": 300.0, "ms_per_src_word": 300.0}}
NEW_KEYS = ("dur_ratio", "backlog", "dub_ms", "dub_raw_ms", "slot_ms", "tgt_", "budget_chars", "budget_ms", "ctl",
            "share", "dense", "est_ms", "est0_ms", "reasked", "native")


# ---------- the parts alone ----------
def test_letters_counts_what_is_spoken_in_any_script():
    assert dense.letters("game chat") == 8
    assert dense.letters("கேம், சாட்!") == 8          # vowel signs count, punctuation and spaces do not
    assert dense.letters("") == 0


def test_expansion_model_turns_a_slot_into_a_length_and_learns_from_lines():
    m = ExpansionModel(SEED)
    assert m.budget(TA, "gpu", 2400) == (8, 40)        # 2.4 s at 300 ms a word and 60 ms a letter
    assert m.estimate_ms(TA, "gpu", LINE10) == 3600
    assert m.budget("bn-IN", "gpu", 2400) is None and m.estimate_ms("bn-IN", "gpu", LINE6) is None
    assert m.get(TA, "stock") is m.get(TA, "gpu")      # another voice of the language: the first guess
    m.note(TA, "gpu", 8, 10, 60, 6000)                 # this voice is slower: 100 ms a letter
    r = m.get(TA, "gpu")
    assert 75 < r.ms_per_char < 85 and r.n == 1        # the first line of a session counts for half
    for _ in range(12):
        m.note(TA, "gpu", 8, 10, 60, 6000)
    assert abs(m.get(TA, "gpu").ms_per_char - 100) < 2 and abs(m.get(TA, "gpu").ms_per_word - 600) < 12
    before = m.get(TA, "gpu").ms_per_char
    m.note(TA, "gpu", 2, 2, 12, 3000)                  # a short line (the engine gives it extra time): left out
    m.note(TA, "gpu", 8, 10, 60, 100)                  # a swallowed line: left out
    assert m.get(TA, "gpu").ms_per_char == before
    m.note("bn-IN", "stock", 6, 6, 30, 1800)           # a language without a seed starts with its first line
    assert m.budget("bn-IN", "stock", 1800) == (6, 30)
    assert set(m.state()) == {"bn-IN|stock", "ta-IN|gpu"} and m.state()["ta-IN|gpu"]["seeded"] is True


def test_seed_file_missing_or_broken_gives_an_empty_model(tmp_path):
    assert ExpansionModel.load(tmp_path / "none.json").rates == {}
    (tmp_path / "bad.json").write_text("{", encoding="utf-8")
    assert ExpansionModel.load(tmp_path / "bad.json").rates == {}
    (tmp_path / "ok.json").write_text(json.dumps({"rates": SEED}), encoding="utf-8")
    assert ExpansionModel.load(tmp_path / "ok.json").budget(TA, "gpu", 3000) == (10, 50)


def test_controller_tightens_while_the_backlog_grows_and_lets_go_when_it_is_gone():
    c = RateController()
    assert c.update(0.0, 0.0) == 1.0 and c.update(0.2, 2.0) == 1.0     # in step: the full slot
    first = c.update(2.0, 4.0)
    assert 0.6 < first < 0.8                                            # 2 s behind: clearly less
    for k in range(1, 30):
        c.update(2.0, 4.0 + 2 * k)
    assert c.scale == c.min_scale == 0.6                                # never under the floor
    top = c.integral
    for k in range(1, 6):
        c.update(2.0, 100.0 + k)
    assert c.integral == top                                            # no wind-up beyond what the scale can use
    scales = [c.update(0.0, 110.0 + 3 * k) for k in range(1, 60)]
    assert scales == sorted(scales) and scales[-1] == 1.0               # relaxes step by step, back to the full slot


def test_speaking_share_calls_speech_dense_over_70_percent_and_lets_go_under_60():
    s = SpeakingShare()
    s.add(0, 9000)
    assert s.share(10000) is None and not s.dense(10000)                # too early to say
    s.add(10000, 19000)
    assert s.share(20000) == 0.9 and s.dense(20000)
    s.add(26000, 30000)                                                 # a pause: 22 of the last 30 s
    assert 0.72 < s.share(30000) < 0.75 and s.dense(30000)
    s.add(31000, 36000)                                                 # 70% of the last 30 s: still dense
    assert 0.6 < s.share(36000) <= 0.7 and s.dense(36000)
    assert s.share(60000) < 0.6 and not s.dense(60000)
    assert dense.shorter_words(10, 3600, 2400) == 7 and dense.shorter_words(4, 9000, 500) == 2
    assert dense.dur_ratio(1800, 2000) == 0.9 and dense.dur_ratio(600, 100) == 2.0   # a slot under 0.3 s is not believed


# ---------- in the pipeline ----------
class SilentSTT:
    async def stream(self, frames, lang, **kw):
        async for _ in frames:
            pass
        return
        yield  # pragma: no cover


class LenLLM:
    """Answers with a fixed line and remembers what it was asked for."""

    def __init__(self, reply: str = LINE6) -> None:
        self.reply, self.seen, self.short = reply, [], []

    async def translate_chunk(self, text, target, glossary, context, **kw):
        self.seen.append(kw)
        return self.reply

    async def shorten(self, text, target, max_seconds, max_words=None):
        self.short.append(max_words)
        return " ".join(text.split()[:max_words])


class PacedGpu:
    """A voice engine that takes 60 ms a letter, less when asked to speak faster."""
    enabled, capacity = True, 1

    def __init__(self) -> None:
        self.speeds: list[float | None] = []

    def speaks(self, lang):
        return True

    async def set_ref(self, *a, **kw):
        return {"ok": True}

    async def synth(self, session_id, text, lang, speed=None):
        self.speeds.append(speed)
        return b"\x00\x20" * int(24000 * dense.letters(text) * 0.06 / (speed or 1.0)), 24000


def make(monkeypatch, tmp_path, reply: str = LINE6, **flags):
    s = get_settings()
    for k, v in {"live_warmup": False, "live_merge_max": 1, **flags}.items():
        monkeypatch.setattr(s, k, v)
    monkeypatch.setattr(dense, "SEED_FILE", tmp_path / "no_seed.json")
    store = LocalStore(tmp_path / "db.json")
    monkeypatch.setattr("app.live.pipeline.get_store", lambda: store)
    monkeypatch.setattr("app.live.pipeline.au.tempo_pcm", lambda pcm, sr, tempo: pcm[: int(len(pcm) / tempo) // 2 * 2])
    sess = LiveSession({"id": "d1", "target_langs": [TA], "src_lang": "hi-IN",
                        "voice_from_stream": {"consent_at": "2026-11-24T00:00:00+00:00"}})
    llm, gpu = LenLLM(reply), PacedGpu()
    p = LivePipeline(sess, stt=SilentSTT(), llm=llm, tts=MockTTS(), gpu=gpu)
    p.gpu_ready, p._gpu_sid = True, "v"
    if p._xp is not None:
        p._xp = ExpansionModel(SEED)
    return p, llm, gpu, store, sess


def chunk(p: LivePipeline, start: int, end: int, words: int = 8):
    return p.assembler.make(" ".join(["shabd"] * words), t_start_ms=start, t_end_ms=end, t_final_ms=end)


async def run(p: LivePipeline, sess: LiveSession, chunks: list, sync: bool = True) -> None:
    q = sess.bus.subscribe(TA)
    await p.start()
    if sync:
        p.set_media(0.0, True)
    for c in chunks:
        p._dispatch(c)
    want, ended = {c.seq for c in chunks}, set()
    while ended < want:
        m = await asyncio.wait_for(q.get(), 10)
        if m["type"] == "audio" and m["last"]:
            ended.add(m["seq"])
    await p.stop()


async def timings(store: LocalStore) -> dict[int, dict]:
    return {r["seq"]: r["timings"] for r in await store.select("live_chunks", session_id="d1")}


async def test_flags_off_nothing_new_is_asked_stored_or_built(monkeypatch, tmp_path):
    p, llm, gpu, store, sess = make(monkeypatch, tmp_path)
    assert p._xp is None and p._share is None and p._merger is None and not p._dense_log and p.dense_stats() == {}
    await run(p, sess, [chunk(p, 0, 2000), chunk(p, 2000, 2200, 1)])
    assert all(set(kw) <= {"brief", "native", "max_words"} for kw in llm.seen) and llm.short == []
    t = await timings(store)
    assert len(t) == 2                                                  # the one-word line went out alone, as in v0
    assert not [k for row in t.values() for k in row if k.split(":")[0].startswith(NEW_KEYS)]
    assert gpu.speeds == [1.0, 1.0]


async def test_budget_gives_the_slot_as_words_and_letters_and_shortens_an_answer_that_is_over(monkeypatch, tmp_path):
    p, llm, gpu, store, sess = make(monkeypatch, tmp_path, reply=LINE10, v1_live_budget=True)
    p.running = True
    c = chunk(p, 0, 2400)                                               # 8 words in 2.4 s
    p._pending[c.seq] = {"timings": {}}
    text, untranslated = await p._translate(TA, c, [], None)
    assert llm.seen[-1] == {"max_words": 8, "max_chars": 40, "compact": True, "native": True}
    assert llm.short == [7] and text == LINE7 and not untranslated      # 3.6 s for 2.4 s: once more, 7 of 10 words
    t = p._pending[c.seq]["timings"]
    assert t["budget:ta-IN"] == 8 and t["budget_chars:ta-IN"] == 40 and t["budget_ms:ta-IN"] == 2400
    assert t["reasked:ta-IN"] == 2 and t["est_ms:ta-IN"] == 2520 and t["est0_ms:ta-IN"] == 3600 and t["ctl:ta-IN"] == 1.0
    llm.reply = LINE6                                                   # an answer inside the slot is left alone
    await p._translate(TA, c, [], None)
    assert llm.short == [7] and p._pending[c.seq]["timings"]["est_ms:ta-IN"] == 2160
    p._playhead[TA] = sess.now_ms() + 3000                              # far behind, no controller: 65% of the slot
    await p._translate(TA, c, [], None)
    assert llm.seen[-1]["max_words"] == 5 and llm.seen[-1]["max_chars"] == 26 and llm.seen[-1]["brief"] is True


async def test_budget_keeps_the_first_answer_when_the_shorter_one_is_no_good(monkeypatch, tmp_path):
    p, llm, gpu, store, sess = make(monkeypatch, tmp_path, reply=LINE10, v1_live_budget=True)
    p.running = True
    c = chunk(p, 0, 2400)
    p._pending[c.seq] = {"timings": {}}

    async def latin(text, target, max_seconds, max_words=None):
        return "romanised words only"
    llm.shorten = latin
    assert (await p._translate(TA, c, [], None))[0] == LINE10           # Latin letters would be read as noise
    assert p._pending[c.seq]["timings"]["reasked:ta-IN"] == 1

    async def slow(text, target, max_seconds, max_words=None):
        await asyncio.sleep(5)
    llm.shorten = slow
    monkeypatch.setattr(p.s, "v1_budget_reask_timeout_s", 0.05)
    assert (await p._translate(TA, c, [], None))[0] == LINE10           # no answer in time: the first one is spoken


async def test_a_language_without_a_rate_falls_back_to_the_old_word_limit_until_a_line_was_spoken(monkeypatch, tmp_path):
    p, llm, gpu, store, sess = make(monkeypatch, tmp_path, v1_live_budget=True)
    p._xp = ExpansionModel(None)
    p.running = True
    c = chunk(p, 0, 2400)
    p._pending[c.seq] = {"timings": {}}
    await p._translate(TA, c, [], None)
    assert llm.seen[-1] == {"native": True}                             # nothing known: as v0 before its first line
    p._dub_ms_per_word[TA] = 700.0
    await p._translate(TA, c, [], None)
    assert llm.seen[-1] == {"max_words": 4, "native": True}             # v0's limit: 8 x 350 ms x 1.15 / 700 ms
    p._note_dub(TA, "gpu", c, [], LINE6, 2160, 2160, {})
    await p._translate(TA, c, [], None)
    assert llm.seen[-1]["compact"] and llm.seen[-1]["max_chars"] == 40  # from its own first line on


async def test_dub_length_against_its_slot_and_the_backlog_are_stored_per_phrase(monkeypatch, tmp_path):
    p, llm, gpu, store, sess = make(monkeypatch, tmp_path, v1_live_budget=True)
    await run(p, sess, [chunk(p, 0, 2000)])
    t = (await timings(store))[1]
    assert 2120 <= t["dub_ms:ta-IN"] <= 2200 and t["slot_ms:ta-IN"] == 2000     # 36 letters at 60 ms
    assert 1.06 <= t["dur_ratio:ta-IN"] <= 1.1 and t["backlog:ta-IN"] == 0
    assert t["tgt_words:ta-IN"] == 6 and t["tgt_chars:ta-IN"] == 36 and t["dub_raw_ms:ta-IN"] == t["dub_ms:ta-IN"]
    assert p._xp.get(TA, "gpu").n == 1                                          # the line taught the model
    assert p.dense_stats()["expansion"]["ta-IN|gpu"]["n"] == 1


async def test_the_next_phrase_sees_the_backlog_a_long_dub_left(monkeypatch, tmp_path):
    p, llm, gpu, store, sess = make(monkeypatch, tmp_path, reply=LINE10, v1_trace=True, data_dir=str(tmp_path),
                                    live_fit=False)
    await run(p, sess, [chunk(p, 0, 1000), chunk(p, 1000, 2000)])
    t = await timings(store)
    assert t[1]["backlog:ta-IN"] == 0 and 2500 <= t[2]["backlog:ta-IN"] <= 2700   # 3.6 s of dub in a 1 s slot
    assert t[1]["dur_ratio:ta-IN"] >= 3.5
    recs = [r for r in trace.read(1) if r["kind"] == "live_phrase"]
    assert {r["seq"]: r["backlog_ms"] for r in recs} == {1: 0, 2: t[2]["backlog:ta-IN"]}
    live = metrics.live_summary(recs, get_settings())
    assert live["dur_ratio_p50"] >= 3.5 and live["dur_ratio_over_1_pct"] == 100.0 and live["dur_ratio_n"] == 2
    assert live["backlog_p95_ms"] > 2000 and live["per_lang"][TA]["dur_ratio_p90"] >= 3.5
    assert live["usage"]["speaking_pct"] == 100.0 and live["usage"]["words_per_min"] == 480


async def same(text, target, max_seconds, max_words=None):
    return text


async def test_controller_scales_the_budget_and_its_state_is_in_the_metrics(monkeypatch, tmp_path):
    p, llm, gpu, store, sess = make(monkeypatch, tmp_path, reply=LINE10, v1_live_budget=True, v1_live_ratectrl=True)
    llm.shorten = same            # a translator that cannot say it shorter: the dub runs long
    await run(p, sess, [chunk(p, 0, 1000), chunk(p, 1000, 2000), chunk(p, 2000, 3000)])
    t = await timings(store)
    assert t[1]["ctl:ta-IN"] == 1.0 and "ctl_i:ta-IN" in t[1]
    st = p.dense_stats()
    assert st["dense"] is False and st["ratectrl"][TA]["scale"] < 1.0 and st["ratectrl"][TA]["backlog_s"] > 0
    c = chunk(p, 3000, 5400)
    p._pending[c.seq] = {"timings": {}}
    p.running = True
    await p._translate(TA, c, [], None)
    assert llm.seen[-1]["max_words"] < 8                                 # behind: less than the slot would hold


async def test_dense_mode_joins_short_lines_and_allows_the_higher_speed(monkeypatch, tmp_path):
    p, llm, gpu, store, sess = make(monkeypatch, tmp_path, reply=LINE10, v1_live_budget=True, v1_live_ratectrl=True)
    llm.shorten = same
    q = sess.bus.subscribe(TA)
    await p.start()
    p.set_media(0.0, True)
    p._dispatch(chunk(p, 0, 400, 1))
    assert p._merger.held is None and not p._dense                       # not dense: a one-word line goes out alone
    p._dispatch(chunk(p, 400, 20000, 40))                                # 20 s of speech without a pause
    assert p._dense
    p._dispatch(chunk(p, 20000, 20300, 1))
    assert p._merger.held is not None                                    # dense: the short line waits ...
    p._dispatch(chunk(p, 20300, 21300, 8))
    assert p._merger.merged == 1                                         # ... and goes out with the next one
    p._dispatch(chunk(p, 21300, 22300, 8))
    ended: set[int] = set()
    while len(ended) < 4:
        m = await asyncio.wait_for(q.get(), 10)
        if m["type"] == "audio" and m["last"]:
            ended.add(m["seq"])
    await p.stop()
    t = await timings(store)
    assert sorted(t) == [1, 2, 4, 5] and t[4]["dense"] == 1 and t[4]["share"] >= 95
    assert t[4]["tempo:ta-IN"] == 1.4 and t[4]["ctl:ta-IN"] <= 0.9       # dense: tighter budget, up to 1.4x


async def test_native_speed_asks_the_engine_for_part_of_the_speed_up_with_a_pace_floor(monkeypatch, tmp_path):
    p, llm, gpu, store, sess = make(monkeypatch, tmp_path, reply=LINE10, v1_live_native_speed=True)
    await run(p, sess, [chunk(p, 0, 1000), chunk(p, 1000, 2000)])
    t = await timings(store)
    assert gpu.speeds[0] == pytest.approx(1.125)                          # 360 ms a word, never under 320: 1.125x
    assert t[1]["native:ta-IN"] == 1.12 and t[1]["tempo:ta-IN"] == 1.3    # the rest by tempo, the limit as before
    monkeypatch.setattr(p.s, "v1_native_floor_ms", 200)
    p2, llm2, gpu2, store2, sess2 = make(monkeypatch, tmp_path / "b", reply=LINE10, v1_live_native_speed=True)
    await run(p2, sess2, [chunk(p2, 0, 1000), chunk(p2, 1000, 2000)])
    assert gpu2.speeds[0] == pytest.approx(1.2)                           # with a lower floor: the 1.2x cap


# ---------- prompts, seed, watcher ----------
async def test_translators_put_the_letter_cap_and_compact_style_in_the_prompt_only_when_asked(monkeypatch):
    from app.providers.llm_local import LocalLLM
    from app.providers.llm_openai import OpenAILLM
    for cls in (LocalLLM, OpenAILLM):
        llm, seen = cls(), []

        async def chat(system, user, **kw):
            seen.append(system)
            return WORD
        monkeypatch.setattr(llm, "_chat", chat)
        await llm.translate_chunk("aaj hum khelenge", TA, [], [], native=True, max_words=5)
        await llm.translate_chunk("aaj hum khelenge", TA, [], [], native=True, max_words=5, max_chars=26, compact=True)
        assert "letters;" not in seen[0] and "Keep names and numbers" not in seen[0]
        assert "at most 5 words and about 26 letters" in seen[1] and "Keep names and numbers" in seen[1]


def test_seed_is_built_from_what_the_history_holds(tmp_path):
    from eval.v1 import expansion_seed as es
    logs = tmp_path / "sessions" / "v0"
    logs.mkdir(parents=True)
    rows = []
    for k in range(30):     # every phrase starts when the one before it ended: 2 s of dub for 8 source words
        rows.append({"seq": k + 1, "t_speech_ms": 1000 * k, "src_words": 8, "speech_ms": 900, "lang": "pa-IN",
                     "first_audio_ms": 2000, "heard_ms": 5100 + 1000 * k, "late_ms": 1000 * k + 100, "tempo": 1.3 if k % 2 else None,
                     "copied_voice": 1, "on_gpu": 1})
    (logs / "2026-11-20_aaaaaaaa.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    tr = tmp_path / "trace-20261124.jsonl"
    recs = [{"kind": "live_phrase", "session": "s", "seq": k, "lang": TA, "tts": "gpu_voice", "clone": True, "src_words": 8,
             "merged_into": None, "dub_raw_ms": 2400, "tgt_words": 6, "tgt_chars": 40} for k in range(25)]
    tr.write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")
    seed = es.build(tmp_path / "sessions", [str(tr)])
    assert seed["rates"]["ta-IN|gpu"] == {"ms_per_char": 60.0, "ms_per_word": 400.0, "ms_per_src_word": 300.0, "n": 25,
                                          "logs_ms_per_src_word": None, "logs_n": 0}
    assert seed["from_logs_only"]["pa-IN|gpu"]["n"] == 29               # no target length in the logs: no rate
    assert 250 <= seed["from_logs_only"]["pa-IN|gpu"]["ms_per_src_word"] <= 325
    assert ExpansionModel(seed["rates"]).budget(TA, "gpu", 2400) == (6, 40)


def test_stream_watcher_sums_up_dub_length_and_backlog(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "stream_watch_dense", Path(__file__).resolve().parents[2] / "scripts" / "v1" / "stream-watch.py")
    sw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sw)
    chunks = [{"session_id": "s1", "seq": k, "t_speech_ms": 2000 * k, "src_text": "ek do teen chaar",
               "timings": {"t_speech_end": 2000 * k + 1500, "t_translated:ta-IN": 2000 * k + 2000,
                           "t_first_audio:ta-IN": 2000 * k + 3000, "late:ta-IN": 100, "tempo:ta-IN": 1.4 if k == 3 else 1.0,
                           "dur_ratio:ta-IN": 0.8 + 0.1 * k, "backlog:ta-IN": 100 * k, "ctl:ta-IN": 0.9}} for k in range(1, 5)]
    db = tmp_path / "db.json"
    db.write_text(json.dumps({"live_chunks": chunks}), encoding="utf-8")
    text = "\n".join(sw.session_summary(str(db), "s1"))
    assert "dub length / slot p50 1.10 p90 1.20" in text and "backlog p50 300 p95 400 ms" in text
    assert "at 1.4x 25% of 4" in text and "budget scale mean 0.90" in text
    for c in chunks:                                                     # a session from before v1.1: the old lines only
        c["timings"] = {k: v for k, v in c["timings"].items() if not k.startswith(("dur_ratio", "backlog", "ctl"))}
    db.write_text(json.dumps({"live_chunks": chunks}), encoding="utf-8")
    assert "dub length" not in "\n".join(sw.session_summary(str(db), "s1"))


@pytest.mark.parametrize("flag", ["v1_live_budget", "v1_live_ratectrl", "v1_live_native_speed"])
def test_dense_flags_default_off(flag):
    from app.config import Settings
    from app.v1.flags import FLAGS
    assert Settings.model_fields[flag].default is False and getattr(get_settings(), flag) is False and flag in FLAGS


async def test_a_line_that_arrives_late_gets_the_time_that_is_left_and_a_short_line_counts_as_slow(monkeypatch, tmp_path):
    p, llm, gpu, store, sess = make(monkeypatch, tmp_path, v1_live_budget=True)
    p.running = True
    p.set_media(0.0, True)                                              # sync mode, viewers 6 s behind
    await asyncio.sleep(0.05)
    now = sess.now_ms()
    c = p.assembler.make(" ".join(["shabd"] * 20), t_start_ms=now - 7000, t_end_ms=now - 500, t_final_ms=now)
    p._pending[c.seq] = {"timings": {}}
    await p._translate(TA, c, [], None)
    # 6.5 s of speech heard only at its end: the dub can begin in about 1.5 s and the next phrase is due 4 s after that
    assert 3900 <= p._pending[c.seq]["timings"]["budget_ms:ta-IN"] <= 4000
    assert p._pending[c.seq]["timings"]["ctl:ta-IN"] == pytest.approx(0.61, abs=0.02)
    assert p._expected_ms(TA, "gpu", LINE6) == 2160                     # 36 letters at 60 ms
    two = " ".join([WORD] * 2)
    assert p._expected_ms(TA, "gpu", two) == pytest.approx(960)         # the engine says a 2-word line at 0.75 speed
    assert p._expected_ms(TA, "stock", two) == 720                      # a stock voice does not
    c2 = p.assembler.make("shabd shabd", t_start_ms=now, t_end_ms=now + 700, t_final_ms=now + 700)
    p._pending[c2.seq] = {"timings": {}}
    await p._translate(TA, c2, [], None)
    assert llm.seen[-1]["max_words"] == 2 and llm.seen[-1]["max_chars"] == 8   # 0.7 s: 11 letters, 8 at the slow speed
