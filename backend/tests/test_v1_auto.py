"""v1.2 auto mode: the one resolver and the overrides file, the auto budget and its meaning check, the one English
voice chosen from a measurement, a refused line spoken by another voice, the guards. Fake providers only."""
import asyncio
import json
import logging
from pathlib import Path

import pytest

from app.config import BACKEND_DIR, VOICE_BY_LANG, VOICE_BY_LANG_MALE, Settings, get_settings
from app.providers.base import ProviderError
from app.studio.stages import voice as voice_stage
from app.v1 import guards, lineguard, trace, voicechain, warm
from app.v1 import mode as v1mode
from app.v1.dense import AutoGate, MeaningRate, WordRate
from app.v1.flags import flags
from app.v1.meaning import MeaningCheck
from tests import test_v1_dense as d
from tests import test_v1_warm as w
from tests.fakes import FakeLLM, FakeTTS

TA, PA, EN = "ta-IN", "pa-IN", "en-IN"
QUIET = "breaker: off\nlive_degrade: off\n"     # for tests that are not about the ladder


@pytest.fixture
def auto(monkeypatch, tmp_path):
    """Auto mode on the settings the app uses, with an overrides file of the test's own."""
    def use(overrides: str | None = "") -> Path:
        s = get_settings()
        f = tmp_path / "overrides.yaml"
        if overrides is not None:
            f.write_text(overrides, encoding="utf-8")
        monkeypatch.setattr(s, "v1_mode", "auto")
        monkeypatch.setattr(s, "v1_overrides_file", str(f))
        monkeypatch.setattr(s, "v1_log_dir", str(tmp_path / "logs"))
        v1mode.reload()
        return f
    yield use
    v1mode.reload()


# ---------- the resolver ----------
def test_manual_mode_follows_each_setting_and_what_v1_2_added_is_off(monkeypatch):
    s = get_settings()
    assert s.v1_mode == "manual" and not v1mode.is_auto(s)             # the test suite's own mode
    assert not any(v1mode.on(name, s) for name in v1mode.AUTO if name != "hq_adaptive")
    monkeypatch.setattr(s, "v1_live_budget", True)
    assert v1mode.on("live_budget", s) and not v1mode.on("auto_budget", s)
    assert not any(v1mode.on(name, s) for name in v1mode.NEW)
    monkeypatch.setattr(s, "v1_studio_hq", True)
    assert v1mode.on("hq_review", s) and s.v1_hq_review is False        # HQ on means the review is on
    with pytest.raises(KeyError):
        v1mode.on("no_such_feature", s)


def test_auto_is_the_default_and_decides_whatever_the_old_names_say(auto, monkeypatch):
    assert Settings(_env_file=None, v1_mode="auto").v1_mode == "auto" and Settings.model_fields["v1_mode"].default == "auto"
    auto()
    s = get_settings()
    assert v1mode.is_auto(s) and s.v1_trace is False and s.v1_live_budget is False
    for name in ("trace", "router", "api_log", "breaker", "live_degrade", "live_stock_default", "studio_hq", "hq_review",
                 "fit_115", "hq_adaptive", "hq_normalise", "hq_auto_glossary", "live_budget", "auto_budget",
                 "meaning_check", "en_single_voice", "en_auto", "voice_fallback", "script_guard", "shift_check"):
        assert v1mode.on(name, s), name
    monkeypatch.setattr(s, "v1_tts_server", True)                       # an old name set to on switches nothing on
    monkeypatch.setattr(s, "v1_live_late_shorten", True)
    assert not v1mode.on("tts_server", s) and not v1mode.on("live_late_shorten", s) and not v1mode.on("live_backcheck", s)
    f = flags(s)
    assert f["V1_MODE"] == "auto" and f["overrides"] == {} and f["V1_STUDIO_HQ"] is True and f["V1_LIVE_RECORD"] is True
    assert f["auto"] == dict.fromkeys(v1mode.NEW, True)
    monkeypatch.setattr(s, "v1_mode", " Manual ")
    assert not v1mode.is_auto(s)
    monkeypatch.setattr(s, "v1_mode", "something else")                 # anything but manual is auto
    assert v1mode.is_auto(s)


# ---------- the overrides file ----------
def test_overrides_switch_one_behaviour_off_or_pin_a_value_in_auto_mode_only(auto, monkeypatch):
    auto("live_budget: off\nV1_TRACE: false\nen_voice: copy\ntts_server: on\nhq_review: off\nmeaning_check: no\n")
    s = get_settings()
    assert not v1mode.on("live_budget", s) and not v1mode.on("trace", s) and not v1mode.on("meaning_check", s)
    assert v1mode.on("tts_server", s) and v1mode.pin("en_voice", s) == "copy" and v1mode.on("api_log", s)
    assert v1mode.on("hq_review", s)                                    # not while HQ is on: there is no HQ without it
    assert flags(s)["overrides"] == {"live_budget": False, "trace": False, "en_voice": "copy", "tts_server": True,
                                     "hq_review": False, "meaning_check": False}
    monkeypatch.setattr(s, "v1_mode", "manual")                         # manual mode does not read the file
    assert v1mode.overrides(s) == {} and not v1mode.on("tts_server", s) and v1mode.pin("en_voice", s) is None


@pytest.mark.parametrize("text", ["live_budget: [off\n", "- live_budget\n- trace\n", "just a sentence\n", "\x00\x01"])
def test_a_bad_overrides_file_is_logged_and_ignored_and_stops_nothing(auto, caplog, text):
    auto(text)
    with caplog.at_level(logging.ERROR, logger="bharatdub.mode"):
        assert v1mode.overrides() == {} and v1mode.on("live_budget") and v1mode.on("trace")
    assert "overrides" in caplog.text
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app) as c:                                           # the backend starts and answers
        assert c.get("/health").status_code == 200 and c.get("/api/v1/flags").json()["V1_MODE"] == "auto"


def test_an_unknown_name_or_value_is_ignored_and_the_rest_of_the_file_holds(auto, caplog):
    auto("live_budget: off\nno_such_thing: off\ntrace: maybe\nen_voice: loud\n")
    with caplog.at_level(logging.ERROR, logger="bharatdub.mode"):
        assert v1mode.overrides() == {"live_budget": False}
    assert "no_such_thing" in caplog.text and "maybe" in caplog.text and "loud" in caplog.text
    assert v1mode.on("trace") and v1mode.pin("en_voice") is None


def test_a_missing_overrides_file_is_no_overrides(auto):
    f = auto(None)
    assert not f.exists() and v1mode.overrides() == {} and v1mode.on("live_budget")


def test_the_shipped_overrides_file_has_every_entry_commented_out_and_names_every_feature():
    f = BACKEND_DIR / "config" / "overrides.yaml"
    assert v1mode.load(f) == {}
    text = f.read_text(encoding="utf-8")
    assert all(line.startswith("#") or not line.strip() for line in text.splitlines())
    for name in [*v1mode.AUTO, *v1mode.PINS]:
        assert f"# {name}:" in text, name


# ---------- the auto budget's gate ----------
def test_gate_goes_on_when_behind_and_off_only_after_calm_lines_and_a_minimum_time():
    g = AutoGate(min_on_ms=15000, calm_lines=4)
    assert not g.on and g.update(0, backlog_ms=100, dur_ratio=0.9) is None
    assert g.update(2000, backlog_ms=300) is None                        # mean 180: not behind
    assert g.update(4000, backlog_ms=2000) == (True, "behind")           # mean 908
    for k in range(3):                                                   # the backlog is gone at once ...
        assert g.update(6000 + 2000 * k, backlog_ms=0, dur_ratio=0.9) is None and g.on
    for k in range(3, 6):                                                # ... the mean follows; not yet 15 s
        assert g.update(6000 + 2000 * k, backlog_ms=0, dur_ratio=0.9) is None and g.on
    out = None
    for k in range(6, 12):
        out = out or g.update(6000 + 2000 * k, backlog_ms=0, dur_ratio=0.9)
    assert out == (False, "in step") and not g.on


def test_gate_does_not_flap_around_its_threshold_and_knows_long_lines_and_dense_speech():
    g = AutoGate(min_on_ms=0, calm_lines=3)
    changes = [g.update(1000 * k, backlog_ms=450 if k % 2 else 600, dur_ratio=1.0) for k in range(40)]
    assert [c for c in changes if c] == [(True, "behind")]               # on once, never off: 450 is over the off line
    g = AutoGate()
    assert g.update(0, backlog_ms=0, dur_ratio=1.4) == (True, "long")
    g = AutoGate(min_on_ms=0, calm_lines=2)
    assert g.update(0, dense=True) == (True, "dense")
    assert g.update(1000, backlog_ms=0, dur_ratio=0.8, dense=True) is None and g.on    # still dense
    assert g.update(2000, backlog_ms=0, dur_ratio=0.8) is None
    assert g.update(3000) is None and g.on                               # a phrase without a line of this language does not count
    assert g.update(4000, backlog_ms=0, dur_ratio=0.8) == (False, "in step")


def test_word_rate_calls_speech_fast_over_four_words_a_second_until_under_three_point_two():
    r = WordRate()
    r.add(0, 5000, 25)
    assert r.rate(10000) is None and not r.fast(10000)                   # too early to say
    r.add(5000, 20000, 75)
    assert r.rate(20000) == 5.0 and r.fast(20000)
    r.add(26000, 30000, 12)
    assert 3.2 < r.rate(30000) < 4.0 and r.fast(30000)                   # between the two thresholds: still fast
    assert r.rate(60000) < 3.2 and not r.fast(60000)


# ---------- the meaning rate ----------
def test_meaning_rate_loosens_a_step_over_the_limit_measures_afresh_and_tightens_slowly():
    m = MeaningRate(window=8, min_samples=4, max_rate=0.25, low_rate=0.10, max_steps=2, tighten_after_s=100)
    for k in range(3):
        assert m.add(budgeted=True, lost=True, shift=False, now_s=k, behind=True) is None    # too few to say
    assert m.add(budgeted=False, lost=True, shift=True, now_s=3, behind=True) is None        # not a budgeted line
    change = m.add(budgeted=True, lost=False, shift=False, now_s=4, behind=True)
    assert change["was"] == 0 and change["steps"] == 1 and change["rate"] == 0.75 and "looser" in change["why"]
    assert m.rate() is None                                              # measured afresh after a step
    for k in range(4):
        change = m.add(budgeted=True, lost=k < 2, shift=False, now_s=10 + k, behind=True)
    assert change["steps"] == 2 and m.steps == 2                         # the last step: translated in full
    assert m.add(budgeted=True, lost=True, shift=False, now_s=20, behind=True) is None       # never past the last step
    assert m.tick(60, True) is None and m.tick(200, False) is None       # not before its time, not unless behind
    back = m.tick(200, True)
    assert back["steps"] == 1 and "trial" in back["why"]
    for k in range(4):
        change = m.add(budgeted=True, lost=False, shift=False, now_s=210 + k, behind=True)
    assert change is None                                                # low, but the last step is only 13 s old
    change = m.add(budgeted=True, lost=False, shift=False, now_s=320, behind=False)
    assert change is None                                                # low and old enough, but the dub is not behind
    change = m.add(budgeted=True, lost=False, shift=False, now_s=321, behind=True)
    assert change["steps"] == 0 and "tighter" in change["why"]
    st = m.state()
    assert st["judged"] == 16 and st["shifted"] == 1 and st["lost_budgeted"] == 6 and st["steps"] == 0


class Judge:
    """Says what it is told to say about every line; can be held back to show that nothing waits for it."""

    def __init__(self, lost: bool = False, shift: bool = False) -> None:
        self.lost, self.shift, self.asked = lost, shift, []
        self.go = asyncio.Event()
        self.go.set()

    async def judge_lines(self, pairs, target):
        await self.go.wait()
        self.asked.append((target, list(pairs)))
        return [{"lost": self.lost, "shift": self.shift} for _ in pairs]


async def test_meaning_check_takes_a_sample_never_more_than_its_queue_and_is_off_without_a_judge(monkeypatch):
    s = get_settings()
    for k, v in {"v1_meaning_sample_every": 2, "v1_meaning_idle_every": 3, "v1_meaning_queue": 2}.items():
        monkeypatch.setattr(s, k, v)
    m = MeaningCheck(Judge(), "s1", [TA], s, now_ms=lambda: 0, behind=lambda lang: True)
    took = [m.offer(TA, k, "source", "dub", True) for k in range(8)]
    assert took == [False, True, False, True, False, False, False, False]   # every second line, then the queue is full
    assert m.sampled == 2 and m.not_judged == 2
    assert [m.offer(TA, k, "source", "dub", False) for k in range(3)] == [False, False, False]   # idle: every third, and full
    assert not m.offer("bn-IN", 1, "s", "d", True) and not m.offer(TA, 9, "", "d", True)
    assert not MeaningCheck(object(), "s1", [TA], s, now_ms=lambda: 0, behind=lambda lang: True).offer(TA, 1, "s", "d", True)


# ---------- the auto budget in the pipeline ----------
def auto_make(auto, monkeypatch, tmp_path, overrides: str = QUIET, judge=None, **settings):
    auto(overrides)
    p, llm, gpu, store, sess = d.make(monkeypatch, tmp_path, **settings)
    if judge is not None:
        p._meaning = MeaningCheck(judge, sess.id, sess.langs, p.s, now_ms=sess.now_ms, behind=p._is_behind)
    return p, llm, gpu, store, sess


async def test_normal_speech_gets_the_full_prompt_and_the_budget_comes_on_when_the_dub_falls_behind(auto, monkeypatch, tmp_path):
    p, llm, gpu, store, sess = auto_make(auto, monkeypatch, tmp_path, reply=d.LINE10)
    assert p._auto and p._budget and p._merger is not None and p._xp is not None and p._fallback and p._script_guard
    p.running = True
    c = d.chunk(p, 0, 2400)
    p._pending[c.seq] = {"timings": {}}
    await p._translate(TA, c, [], None)
    assert llm.seen[-1] == {"native": True} and llm.short == []          # in step: no limit, no "be brief", no second ask
    assert p._pending[c.seq]["timings"]["auto:ta-IN"] == 0
    p._dub_ms_per_word[TA] = 700                                         # v0's word limit would apply here: not in auto
    await p._translate(TA, c, [], None)
    assert llm.seen[-1] == {"native": True}
    p._gate_update(TA, 5000, c.seq, backlog_ms=2500)                     # two lines with a backlog
    assert p._budget_now(TA) and p.auto_log[-1]["why"] == "behind" and p.auto_log[-1]["on"] is True
    await p._translate(TA, c, [], None)
    assert llm.seen[-1]["compact"] is True and llm.seen[-1]["max_words"] <= 8 and llm.short     # the slot as a length, checked
    t = p._pending[c.seq]["timings"]
    assert t["auto:ta-IN"] == 1 and t["budget_ms:ta-IN"] == 2400
    st = p.dense_stats()
    assert st["auto_budget"][TA]["on"] is True and st["auto_budget"][TA]["why"] == "behind" and len(st["auto_budget_log"]) == 1


async def test_the_budget_goes_off_again_once_the_dub_is_in_step_and_every_change_is_in_the_trace(auto, monkeypatch, tmp_path):
    seen: list[dict] = []
    monkeypatch.setattr(trace, "write", lambda rec: seen.append(rec))
    p, llm, gpu, store, sess = auto_make(auto, monkeypatch, tmp_path, v1_auto_min_on_ms=0, v1_auto_calm_lines=2)
    p._gate_update(TA, 1000, 1, backlog_ms=3000)
    assert p._budget_now(TA)
    for k in range(12):
        p._gate_update(TA, 2000 + 1000 * k, 2 + k, backlog_ms=0, dur_ratio=0.9)
    assert not p._budget_now(TA)
    assert [(r["on"], r["why"]) for r in p.auto_log] == [(True, "behind"), (False, "in step")]
    events = [r for r in seen if r["kind"] == "live_auto_budget"]
    assert [(r["on"], r["why"], r["lang"]) for r in events] == [(True, "behind", TA), (False, "in step", TA)]


async def test_a_phrase_whose_turn_comes_after_its_moment_counts_as_behind(auto, monkeypatch, tmp_path):
    """Sound that is made late (a slow voice, a stall) leaves nothing queued, so the backlog alone would not see it."""
    p, llm, gpu, store, sess = auto_make(auto, monkeypatch, tmp_path, live_sync_delay_ms=500)
    quick = llm.translate_chunk

    async def slow(text, target, glossary, context, **kw):
        await asyncio.sleep(1.3)
        return await quick(text, target, glossary, context, **kw)
    llm.translate_chunk = slow
    await d.run(p, sess, [d.chunk(p, 0, 400, 6)])                        # due at 0.5 s; its text is there at 1.3 s
    assert p.auto_log and p.auto_log[0]["why"] == "behind" and p.auto_log[0]["backlog_ms"] >= 600
    assert (await d.timings(store))[1]["backlog:ta-IN"] == 0             # nothing was queued in front of it


async def test_dense_speech_switches_the_budget_on_joins_short_lines_and_the_controller_scales_it(auto, monkeypatch, tmp_path):
    async def same(text, target, max_seconds, max_words=None):
        return text
    p, llm, gpu, store, sess = auto_make(auto, monkeypatch, tmp_path, reply=d.LINE10)
    llm.shorten = same            # a translator that cannot say it shorter: the dub runs long
    q = sess.bus.subscribe(TA)
    await p.start()
    p.set_media(0.0, True)
    p._dispatch(d.chunk(p, 0, 400, 1))
    assert p._merger.held is None and not p._dense                       # not dense: a one-word line goes out alone
    p._dispatch(d.chunk(p, 400, 20000, 40))                              # 20 s of speech without a pause
    assert p._dense and p._budget_now(TA)
    p._dispatch(d.chunk(p, 20000, 20300, 1))
    assert p._merger.held is not None                                    # dense: the short line waits ...
    p._dispatch(d.chunk(p, 20300, 21300, 8))
    assert p._merger.merged == 1                                         # ... and goes out with the next one
    p._dispatch(d.chunk(p, 21300, 22300, 8))
    ended: set[int] = set()
    while len(ended) < 4:
        m = await asyncio.wait_for(q.get(), 10)
        if m["type"] == "audio" and m["last"]:
            ended.add(m["seq"])
    await p.stop()
    t = await d.timings(store)
    assert sorted(t) == [1, 2, 4, 5] and t[4]["dense"] == 1 and t[4]["share"] >= 95 and t[4]["auto:ta-IN"] == 1
    assert t[4]["ctl:ta-IN"] <= 0.9 and t[4]["tempo:ta-IN"] <= 1.3       # tighter budget; never over 1.3x (1.4x is unheard)
    st = p.dense_stats()
    assert st["dense"] is True and st["ratectrl"][TA]["scale"] < 1.0 and st["auto_budget"][TA]["on"] is True


async def test_a_language_that_loses_meaning_gets_a_looser_budget_and_no_phrase_waits_for_the_judge(auto, monkeypatch, tmp_path):
    seen: list[dict] = []
    monkeypatch.setattr(trace, "write", lambda rec: seen.append(rec))
    judge = Judge(lost=True)
    judge.go.clear()                                                     # the judge is slow
    p, llm, gpu, store, sess = auto_make(auto, monkeypatch, tmp_path, judge=judge, v1_meaning_sample_every=1,
                                         v1_meaning_min_samples=2, v1_meaning_window=4, v1_meaning_max_steps=2)
    p._gate_update(TA, 0, 0, backlog_ms=3000)                            # behind: the budget applies
    q = sess.bus.subscribe(TA)
    await p.start()
    p.set_media(0.0, True)
    chunks = [d.chunk(p, 1000 * k, 1000 * k + 1000) for k in range(3)]
    for c in chunks:
        p._dispatch(c)
    ended: set[int] = set()
    while len(ended) < 3:                                                # every line is out ...
        m = await asyncio.wait_for(q.get(), 10)
        if m["type"] == "audio" and m["last"]:
            ended.add(m["seq"])
    assert judge.asked == [] and p._loose_steps(TA) == 0                 # ... before the judge has said a word
    first = (await d.timings(store))[1]
    assert first["auto:ta-IN"] == 1 and first["judged:ta-IN"] == 1 and "loose:ta-IN" not in first
    judge.go.set()
    for _ in range(100):
        if p._loose_steps(TA):
            break
        await asyncio.sleep(0.02)
    assert p._loose_steps(TA) == 1 and judge.asked[0][0] == TA
    before = first["ctl:ta-IN"]
    c = d.chunk(p, 9000, 10000)
    p._pending[c.seq] = {"timings": {}}
    await p._translate(TA, c, [], None)
    t = p._pending[c.seq]["timings"]
    assert t["loose:ta-IN"] == 1 and t["ctl:ta-IN"] >= round(before + 0.1, 2) - 0.01     # one step more of the slot
    stats = p.dense_stats()["meaning"]
    assert stats["by_lang"][TA]["steps"] == 1 and stats["adjustments"][0]["lang"] == TA and "looser" in stats["adjustments"][0]["why"]
    for _ in range(6):                                                   # still losing: the last step, translated in full
        p._meaning._note(TA, 99, True, {"lost": True, "shift": False})
    assert p._loose_steps(TA) == 2 and not p._budget_now(TA)
    await p.stop()
    kinds = [r["kind"] for r in seen]
    assert "live_meaning" in kinds and kinds.count("live_budget_adjust") == 2
    rec = next(r for r in seen if r["kind"] == "live_meaning")
    assert rec["lost"] is True and rec["budgeted"] is True and "rate" in rec and "text" not in rec


async def test_overrides_switch_the_auto_budget_or_the_whole_budget_off(auto, monkeypatch, tmp_path):
    p, llm, gpu, store, sess = auto_make(auto, monkeypatch, tmp_path, QUIET + "auto_budget: off\n")
    assert p._budget and not p._auto and p._merger is None               # the budget on every phrase, in two steps
    p.running = True
    c = d.chunk(p, 0, 2400)
    p._pending[c.seq] = {"timings": {}}
    await p._translate(TA, c, [], None)
    assert llm.seen[-1]["compact"] is True and "auto:ta-IN" not in p._pending[c.seq]["timings"]
    p, llm, gpu, store, sess = auto_make(auto, monkeypatch, tmp_path / "b", QUIET + "live_budget: off\n")
    assert not p._budget and not p._auto and p._xp is None


# ---------- the one English voice ----------
class SlowCopy(w.RecTTS):
    """The hosted voice whose copy takes `copy_s` for a line."""

    def __init__(self, copy_s: float = 0.0) -> None:
        super().__init__()
        self.copy_s = copy_s

    async def synth_stream(self, text, lang, voice, *, sample_rate=None, speed=1.0):
        if voice["kind"] == "clone":
            await asyncio.sleep(self.copy_s)
        async for chunk in super().synth_stream(text, lang, voice, sample_rate=sample_rate, speed=speed):
            yield chunk


async def en_session(auto, monkeypatch, tmp_path, tts, *, copy: bool = True, overrides: str = QUIET, row=None, **settings):
    tmp_path.mkdir(exist_ok=True)
    auto(overrides)
    p, sess, llm, _, gpu, store = w.setup(monkeypatch, tmp_path, [EN, PA], row if row is not None else {"engine": "gpu"}, **settings)
    p.tts = tts
    if copy:
        sess.row["voice_profile_id"] = await w.profile_with_copy(store)
    qs = {EN: sess.bus.subscribe(EN)}
    await p.start()
    p.set_media(0.0, True)
    await asyncio.wait_for(p._en_decided.wait(), 5)
    return p, sess, qs, store


async def test_english_voice_is_measured_at_the_start_chosen_once_and_kept(auto, monkeypatch, tmp_path):
    seen: list[dict] = []
    monkeypatch.setattr(trace, "write", lambda rec: seen.append(rec))
    tts = SlowCopy(0.0)
    p, sess, qs, store = await en_session(auto, monkeypatch, tmp_path, tts)
    assert tts.said[0] == (EN, "clone", warm.EN_PROBE_LINE)             # one probe line, in the copy
    c = p.en_choice
    assert p._en_mode == "copy" and c["voice"] == "copy" and c["probe_ms"] <= c["available_ms"] == 6000 - 3800
    assert sess.row["en_voice"]["voice"] == "copy" and "within" in c["why"]
    tts.said.clear()
    await w.say(p, qs, ago_ms=5000)         # 1 s before it is due: v0 would take a stock voice here
    await w.say(p, qs)
    assert w.en_voices(tts) == ["clone", "clone"]
    p._en_set("stock", "a second choice")                               # there is no second choice
    await w.say(p, qs)
    assert p._en_mode == "copy" and w.en_voices(tts) == ["clone"] * 3
    await p.stop()
    assert (await store.get("live_sessions", "w1") or sess.row)["en_voice"]["voice"] == "copy"
    events = [r for r in seen if r["kind"] == "live_en_voice"]
    assert len(events) == 1 and events[0]["mode"] == "copy" and events[0]["probe_ms"] == c["probe_ms"]
    assert p.warm_stats()["en_voice_choice"]["why"] == c["why"]


async def test_a_copy_that_is_too_slow_or_does_not_answer_gives_the_one_stock_voice(auto, monkeypatch, tmp_path):
    tts = SlowCopy(0.4)
    p, sess, qs, store = await en_session(auto, monkeypatch, tmp_path, tts, v1_en_pipeline_ms=5800)   # a line has 0.2 s
    c = p.en_choice
    assert p._en_mode == "stock" and c["probe_ms"] >= 400 and c["available_ms"] == 200 and "more than" in c["why"]
    tts.said.clear()
    await w.say(p, qs)                      # 6 s before it is due and the copy is there: the stock voice all the same
    assert w.en_voices(tts) == [VOICE_BY_LANG[EN]]
    await p.stop()
    tts = SlowCopy(0.0)
    tts.dead = {"clone"}
    p, sess, qs, store = await en_session(auto, monkeypatch, tmp_path / "b", tts)
    assert p._en_mode == "stock" and p.en_choice["probe_ms"] is None and "did not answer" in p.en_choice["why"]
    await p.stop()
    tts = SlowCopy(5.0)
    p, sess, qs, store = await en_session(auto, monkeypatch, tmp_path / "c", tts, v1_en_probe_timeout_s=0.2)
    assert p._en_mode == "stock" and "no answer in" in p.en_choice["why"]
    await p.stop()


async def test_without_a_copy_at_the_start_or_with_a_pinned_voice_nothing_is_measured(auto, monkeypatch, tmp_path):
    tts = SlowCopy()
    p, sess, qs, store = await en_session(auto, monkeypatch, tmp_path, tts, copy=False)
    assert p._en_mode == "stock" and tts.said == [] and "no copied voice" in p.en_choice["why"]
    await p.stop()
    tts = SlowCopy()
    p, sess, qs, store = await en_session(auto, monkeypatch, tmp_path / "b", tts, overrides=QUIET + "en_voice: stock\n")
    assert p._en_mode == "stock" and tts.said == [] and p.en_choice["why"] == "pinned in overrides.yaml"
    await p.stop()
    tts = SlowCopy()                        # auto mode: also a session on the hosted engine
    p, sess, qs, store = await en_session(auto, monkeypatch, tmp_path / "c", tts, row={})
    assert p._en_mode == "copy" and p.engine is None
    await p.stop()
    tts = SlowCopy()                        # and off with its switch
    p, sess, qs, store = await en_session(auto, monkeypatch, tmp_path / "e", tts, overrides=QUIET + "en_single_voice: off\n")
    assert p._en_mode is None and tts.said == []
    await p.stop()


async def test_the_ladder_may_still_step_english_down_on_failure_and_it_is_logged(auto, monkeypatch, tmp_path):
    tts = SlowCopy()
    p, sess, qs, store = await en_session(auto, monkeypatch, tmp_path, tts, overrides="breaker: off\n",
                                          v1_degrade_probe_ms=600000)
    assert p._en_mode == "copy" and p._ladder is not None
    tts.dead = {"clone"}
    tts.said.clear()
    got = await w.say(p, qs)                # the copy fails, also when asked again: the stock voice says this line
    assert len(w.pcm_of(got[EN])) > 0 and w.en_voices(tts) == ["clone", "clone", VOICE_BY_LANG[EN]]
    assert p._en_mode == "copy"                                          # the session's choice is not changed by it
    ev = p.voice_events[-1]
    assert ev["tried"] == ["copy", "stock"] and ev["spoken_by"] == "stock" and ev["failed"][0]["voice"] == "copy"
    await p.stop()
    t = await w.stored(store)
    assert t[max(t)]["voice_fb:en-IN"] == "copy>stock"


# ---------- a refused line is spoken by another voice ----------
async def live(auto, monkeypatch, tmp_path, langs, tts, overrides: str = QUIET, row=None, **settings):
    auto(overrides)
    p, sess, llm, _, gpu, store = w.setup(monkeypatch, tmp_path, langs, row or {}, **settings)
    p.tts = tts
    gpu.enabled = False
    qs = {lg: sess.bus.subscribe(lg) for lg in langs}
    await p.start()
    return p, sess, qs, store, gpu


async def test_a_line_the_stock_voice_refuses_is_asked_again_then_spoken_by_another_voice(auto, monkeypatch, tmp_path):
    seen: list[dict] = []
    monkeypatch.setattr(trace, "write", lambda rec: seen.append(rec))
    tts = w.RecTTS()
    tts.dead = {VOICE_BY_LANG[PA]}
    p, sess, qs, store, gpu = await live(auto, monkeypatch, tmp_path, [PA], tts)
    got = await w.say(p, qs)
    assert len(w.pcm_of(got[PA])) > 0                                    # the line has sound
    assert [name for _, name, _ in tts.said] == [VOICE_BY_LANG[PA], VOICE_BY_LANG[PA], VOICE_BY_LANG_MALE[PA]]
    ev = p.voice_events[-1]
    assert ev["tried"] == ["stock", "stock_alt"] and ev["spoken_by"] == "stock_alt" and p.unspoken == 0
    await p.stop()
    t = (await w.stored(store))[1]
    assert t["voice_fb:pa-IN"] == "stock>stock_alt" and t["tts_retry:pa-IN"] == 1 and "unspoken:pa-IN" not in t
    rec = next(r for r in seen if r["kind"] == "live_voice_fallback")
    assert rec["spoken_by"] == "stock_alt" and rec["failed"][0]["voice"] == "stock" and "unknown voice" in rec["failed"][0]["error"]
    phrase = next(r for r in seen if r["kind"] == "live_phrase")
    assert phrase["voice_fallback"] == "stock>stock_alt" and phrase["unspoken"] is None
    assert p.dense_stats()["unspoken"] == 0 and len(p.dense_stats()["voice_events"]) == 1


async def test_only_when_every_voice_fails_is_a_line_unspoken_and_it_is_marked_and_logged(auto, monkeypatch, tmp_path, caplog):
    seen: list[dict] = []
    monkeypatch.setattr(trace, "write", lambda rec: seen.append(rec))
    tts = w.RecTTS()
    tts.dead = {VOICE_BY_LANG[PA], VOICE_BY_LANG_MALE[PA], "clone"}
    p, sess, qs, store, gpu = await live(auto, monkeypatch, tmp_path, [PA], tts)
    p.voice = {"kind": "clone", "embedding": w.EMB}                      # the session has a hosted copy too
    console = sess.bus.subscribe("*")
    with caplog.at_level(logging.ERROR, logger="live"):
        got = await w.say(p, qs, ago_ms=6000)                            # late: a stock voice is asked first
    assert len(w.pcm_of(got[PA])) == 0
    assert {name for _, name, _ in tts.said} == {VOICE_BY_LANG[PA], VOICE_BY_LANG_MALE[PA], "clone"}
    ev = p.voice_events[-1]
    assert sorted(ev["tried"]) == ["copy", "stock", "stock_alt"] and ev["spoken_by"] is None and p.unspoken == 1
    assert "NO SOUND" in caplog.text
    await p.stop()
    t = (await w.stored(store))[1]
    assert t["unspoken:pa-IN"] == "no_voice" and "voice_fb:pa-IN" not in t
    phrase = next(r for r in seen if r["kind"] == "live_phrase")
    assert phrase["unspoken"] == "no_voice"
    end = next(r for r in seen if r["kind"] == "live_session_end")
    assert end["unspoken"] == 1 and end["mode"] == "auto"
    errors = []
    while not console.empty():
        m = console.get_nowait()
        if m.get("type") == "error":
            errors.append(m["message"])
    assert any("no voice could say a line" in e for e in errors)


async def test_our_engine_failing_goes_to_the_hosted_copy_then_stock_and_a_dead_hosted_voice_to_our_engine(auto, monkeypatch, tmp_path):
    tts = w.RecTTS()
    tts.dead = {"clone"}
    p, sess, qs, store, gpu = await live(auto, monkeypatch, tmp_path, [TA], tts)
    gpu.enabled, p.gpu_ready, p._gpu_sid = True, True, "v"
    p.voice = {"kind": "clone", "embedding": w.EMB}

    async def down(*a, **kw):
        raise ProviderError("gpu: ConnectError", retryable=True)
    ok, gpu.synth = gpu.synth, down
    got = await w.say(p, qs)
    assert len(w.pcm_of(got[TA])) > 0 and p.voice_events[-1]["tried"] == ["gpu", "copy", "stock"]
    assert p.voice_events[-1]["spoken_by"] == "stock"
    # The other way round: the engine is not the first choice (it is "down"), the hosted voices refuse, it answers.
    gpu.synth = ok
    p._gpu_fail, p._gpu_retry_at = 5, 10**9
    tts.dead = {"clone", VOICE_BY_LANG[TA]}                              # Tamil has one stock voice only
    got = await w.say(p, qs, ago_ms=6000)
    assert len(w.pcm_of(got[TA])) > 0 and p.voice_events[-1]["spoken_by"] == "gpu"
    assert p.voice_events[-1]["tried"][-1] == "gpu" and p.unspoken == 0
    await p.stop()


async def test_a_line_whose_translation_failed_is_marked_too(auto, monkeypatch, tmp_path):
    p, sess, qs, store, gpu = await live(auto, monkeypatch, tmp_path, [PA], w.RecTTS())

    async def broken(text, target, glossary, context, **kw):
        raise ProviderError("llm: HTTP 500")
    p.llm.translate_chunk = broken
    got = await w.say(p, qs)
    assert len(w.pcm_of(got[PA])) == 0 and p.unspoken == 1 and p.voice_events[-1]["why"] == "untranslated"
    await p.stop()
    assert (await w.stored(store))[1]["unspoken:pa-IN"] == "untranslated"


def test_the_order_of_voices_is_written_in_one_place():
    assert voicechain.ORDER == ("gpu", "copy", "stock", "stock_alt")
    assert voicechain.rest(["stock"], {"gpu", "copy", "stock", "stock_alt"}) == ["gpu", "copy", "stock_alt"]
    assert voicechain.rest(["gpu", "copy"], {"gpu", "copy", "stock"}) == ["stock"]
    assert voicechain.stock_alt(PA)["voice"] == VOICE_BY_LANG_MALE[PA] and voicechain.stock_alt(TA) is None


# ---------- the guards, Live ----------
DEVANAGARI = "यह हिंदी में ही रह गया"
TAMIL = "இது தமிழில் உள்ளது"


async def test_script_guard_translates_a_wrong_script_line_once_more_and_flags_it_when_it_is_still_wrong(auto, monkeypatch, tmp_path):
    p, sess, qs, store, gpu = await live(auto, monkeypatch, tmp_path, [TA], w.RecTTS())
    replies = [DEVANAGARI, TAMIL, DEVANAGARI, DEVANAGARI, TAMIL]

    async def answer(text, target, glossary, context, **kw):
        return replies.pop(0)
    p.llm.translate_chunk = answer
    for _ in range(3):
        await w.say(p, qs)
    await p.stop()
    t = await w.stored(store)
    assert [t[k].get("script:ta-IN") for k in sorted(t)] == [1, 2, None]         # put right, flagged, fine
    assert p.guard == {"script_checked": 3, "script_failed": 2, "script_regenerated": 1, "script_flagged": 1,
                       "src_checked": 3, "src_failed": 0}
    assert p.dense_stats()["guard"]["script_flagged"] == 1


async def test_a_transcript_in_another_script_than_the_sessions_source_language_is_marked(auto, monkeypatch, tmp_path):
    p, sess, qs, store, gpu = await live(auto, monkeypatch, tmp_path, [PA], w.RecTTS())
    await w.say(p, qs, text="aaj hum game khelenge")                     # Hinglish in Latin letters: fine for Hindi
    await w.say(p, qs, text="এটা বাংলায় লেখা")                           # what `indic-auto` once made of game sound
    await p.stop()
    t = await w.stored(store)
    assert "src_script" not in t[1] and t[2]["src_script"] == 0 and p.guard["src_failed"] == 1 and p.guard["src_checked"] == 2
    assert guards.transcript_script_ok("anything", "indic-auto") is None and guards.transcript_script_ok("hello", "en-IN") is None


def test_the_phrase_record_of_the_trace_carries_the_new_fields(monkeypatch):
    seen: list[dict] = []
    monkeypatch.setattr(trace, "write", lambda rec: seen.append(rec))
    timings = {"t_speech_end": 1000, "t_stt_final": 1100, "src_script": 0, "wps": 4.2,
               "auto:ta-IN": 1, "loose:ta-IN": 2, "judged:ta-IN": 1, "script:ta-IN": 2, "voice_fb:ta-IN": "gpu>stock",
               "t_first_audio:ta-IN": 3000, "auto:pa-IN": 0, "unspoken:pa-IN": "no_voice"}
    trace.live_phrase("s" * 8, {}, 3, {"timings": timings, "src_text": "a b", "t_speech_ms": 0}, {})
    ta, pa = (next(r for r in seen if r["lang"] == lg) for lg in (TA, PA))
    assert (ta["budget_auto"], ta["loose_steps"], ta["judged"], ta["guard_script"], ta["voice_fallback"]) == (True, 2, True, "flagged", "gpu>stock")
    assert ta["src_script_ok"] is False and ta["words_per_s"] == 4.2 and "native" not in ta
    assert pa["budget_auto"] is False and pa["unspoken"] == "no_voice" and pa["guard_script"] is None


def test_the_summary_counts_guards_judged_lines_and_lines_without_sound(monkeypatch):
    from app.v1 import metrics
    recs = [{"kind": "live_phrase", "session": "s", "seq": k, "lang": TA, "first_audio_ms": 2000 if k else None,
             "budget_auto": k % 2 == 0, "guard_script": "flagged" if k == 1 else None,
             "unspoken": "no_voice" if k == 0 else None, "voice_fallback": "stock>stock_alt" if k == 2 else None}
            for k in range(4)]
    recs += [{"kind": "live_meaning", "session": "s", "seq": k, "lang": TA, "budgeted": k < 3, "lost": k == 0, "shift": k == 3}
             for k in range(4)]
    recs += [{"kind": "live_auto_budget", "lang": TA, "on": True}, {"kind": "live_budget_adjust", "lang": TA, "was": 0, "steps": 1}]
    got = metrics.live_summary(recs, get_settings())
    assert (got["budget_auto_on"], got["budget_auto_off"], got["guard_script_failed"], got["guard_script_flagged"]) == (2, 2, 1, 1)
    assert (got["unspoken"], got["voice_fallback"], got["silent_unmarked"]) == (1, 1, 0)
    assert got["meaning"] == {"judged": 4, "shifted": 1, "shift_pct": 25.0, "judged_budgeted": 3, "lost_budgeted": 1,
                              "loss_pct": 33.3, "lost_any": 1}
    assert got["per_lang"][TA]["meaning"]["judged"] == 4 and got["budget_switches"] == 1 and got["budget_looser"] == 1


# ---------- the guards, Studio ----------
class LineJudge:
    """Fails the lines whose dub contains a marked word: `SHIFT` or `LOST`."""

    def __init__(self) -> None:
        self.calls = 0

    async def judge_lines(self, pairs, target):
        self.calls += 1
        return [{"shift": "SHIFT" in dub, "lost": "LOST" in dub} for _, dub in pairs]


async def test_studio_guard_regenerates_once_then_flags_and_counts_each_guard_apart():
    src = ["ek", "do", "teen", "chaar", "paanch"]
    out = [TAMIL, DEVANAGARI, DEVANAGARI, "SHIFT " + TAMIL, "LOST " + TAMIL]
    asked: list[list[int]] = []

    async def again(idx):
        asked.append(list(idx))
        return {(1,): [TAMIL], (2,): [DEVANAGARI], (3, 4): [TAMIL + " சரி", "LOST again " + TAMIL]}[tuple(idx)] \
            if tuple(idx) != (1, 2) else [TAMIL, DEVANAGARI]
    lines, v = await lineguard.check(src, out, TA, judge=LineJudge(), retranslate=again)
    assert asked == [[1, 2], [3, 4]]
    assert [x["script"] for x in v] == ["ok", "regenerated", "flagged", "ok", "ok"]
    assert [x["shift"] for x in v] == ["ok", "ok", "ok", "regenerated", "flagged"]
    assert lines == [TAMIL, TAMIL, DEVANAGARI, TAMIL + " சரி", "LOST " + TAMIL]      # a flagged line keeps its first answer
    assert "another script" in v[2]["why"] and "missing" in v[4]["why"]
    assert lineguard.summary(v) == {"lines": 5, "script_checked": 5, "script_failed": 2, "script_flagged": 1,
                                    "shift_checked": 5, "shift_not_checked": 0, "shift_failed": 2, "shift_flagged": 1}
    assert lineguard.flag_fields(v[4]) == {"guard": {"script": "ok", "shift": "flagged", "why": v[4]["why"]}, "flagged": True,
                                           "flag_reason": "guard: " + v[4]["why"]}
    assert lineguard.flag_fields(v[0]) == {"guard": {"script": "ok", "shift": "ok"}, "flagged": False, "flag_reason": ""}


async def test_a_line_the_judge_did_not_answer_for_is_not_checked_never_passed():
    async def again(idx):
        raise AssertionError("nothing to translate again")
    lines, v = await lineguard.check(["ek"], [TAMIL], TA, judge=object(), retranslate=again)
    assert v == [{"script": "ok", "shift": "not_checked"}] and lineguard.summary(v)["shift_checked"] == 0
    lines, v = await lineguard.check(["ek"], [TAMIL], TA, judge=object(), retranslate=again, shift=False)
    assert v == [{"script": "ok"}]
    assert guards.parse_verdicts('here: [{"shift": true, "lost": false}]', 1) == [{"shift": True, "lost": False}]
    assert guards.parse_verdicts('[{"shift": true}]', 2) is None and guards.parse_verdicts("no", 1) is None


class PickyTTS(FakeTTS):
    """Refuses the voices named in `dead` (a stock voice's name, or "clone")."""

    def __init__(self, dead: set[str]) -> None:
        super().__init__()
        self.dead, self.asked = dead, []

    async def synth(self, text, lang, voice):
        name = "clone" if voice["kind"] == "clone" else voice["voice"]
        self.asked.append(name)
        if name in self.dead:
            raise ProviderError("tts: HTTP 502 technical difficulties", status=502)
        return await super().synth(text, lang, voice)


async def test_studio_line_the_voice_refuses_is_spoken_by_the_next_voice_and_raises_only_when_all_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path))
    clone = {"kind": "clone", "embedding": w.EMB}
    usage, warnings = {}, []
    tts = PickyTTS({"clone", VOICE_BY_LANG[PA]})
    path = await voice_stage.synth_line(tts, "ik do tin", PA, clone, "m", 44100, usage, warnings, fallback=True)
    assert path.exists() and tts.asked == ["clone", VOICE_BY_LANG[PA], VOICE_BY_LANG_MALE[PA]]
    assert usage["voice_fallbacks"] == 1 and "spoken by the stock_alt voice" in warnings[-1]
    tts = PickyTTS({"clone", VOICE_BY_LANG[TA]})
    with pytest.raises(voice_stage.NoVoice) as e:
        await voice_stage.synth_line(tts, "onru irandu", TA, clone, "m", 44100, {}, [], fallback=True)
    assert [t["voice"] for t in e.value.tried] == ["copy", "stock"] and "502" in e.value.tried[0]["error"]
    tts = PickyTTS({VOICE_BY_LANG[TA]})                                  # manual mode: a refused stock line fails, as before
    with pytest.raises(ProviderError):
        await voice_stage.synth_line(tts, "moonru naangu", TA, voice_stage.stock_voice(TA), "m", 44100, {}, [])


class GuardLLM(FakeLLM):
    """Translates as the fake does, but the second line comes out in the wrong script the first time; judges."""

    def __init__(self) -> None:
        super().__init__()
        self.judged = 0

    async def translate_batch(self, lines, target, glossary):
        self.batch_calls += 1
        if len(lines) == 3:
            return [f"{target} {lines[0]}", DEVANAGARI, f"SHIFT {target} {lines[2]}"]
        return [f"{target} again {line}" for line in lines]

    async def judge_lines(self, pairs, target):
        self.judged += 1
        return [{"shift": "SHIFT" in dub, "lost": False} for _, dub in pairs]


@pytest.mark.skipif(not __import__("tests.test_studio_pipeline", fromlist=["x"])._has_ffmpeg(), reason="ffmpeg not installed")
async def test_studio_job_in_auto_mode_guards_every_line_and_finishes_with_a_line_no_voice_could_say(tmp_path, monkeypatch):
    from app.db import LocalStore
    from app.studio.runner import StudioRunner
    from app.studio.stages import segment
    from tests import test_studio_pipeline as sp
    monkeypatch.setattr(segment, "vad", lambda audio: list(sp.SEGS))
    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path / "data"))
    s = get_settings().model_copy(update={"studio_separate": False, "llm_model": "fake", "v1_mode": "auto",
                                          "v1_overrides_file": str(tmp_path / "none.yaml"), "data_dir": str(tmp_path / "data")})
    v1mode.reload()
    llm, tts = GuardLLM(), PickyTTS(set())
    real = tts.synth

    async def synth(text, lang, voice):                                  # no voice at all for the first line
        if "src_000" in text:
            tts.asked.append("refused")
            raise ProviderError("tts: HTTP 502 technical difficulties", status=502)
        return await real(text, lang, voice)
    tts.synth = synth
    r = StudioRunner(store=LocalStore(tmp_path / "db.json"), stt=sp.FakeSTT(), llm=llm, tts=tts, settings=s)
    job_id = await sp.new_job(r, tmp_path, lang=PA)
    job = await r.store.get("jobs", job_id)
    assert job["status"] == "done", job.get("error")                     # the job is finished, not failed
    segs = await r.store.select("segments", order="idx", job_id=job_id)
    trs = {t["segment_id"]: t for t in await r.store.select("translations", lang=PA)}
    rows = [trs[x["id"]] for x in segs]
    assert rows[0]["unspoken"] is True and rows[0]["flagged"] and "no voice could say this line" in rows[0]["flag_reason"]
    assert not rows[0].get("audio_path") and rows[1]["audio_path"] and rows[2]["audio_path"]
    assert rows[1]["guard"]["script"] == "regenerated" and rows[1]["text"].startswith("pa-IN again")
    assert rows[2]["guard"]["shift"] == "regenerated" and not rows[2]["flagged"]
    g = job["stage_timings"]["_guards"][PA]
    assert (g["lines"], g["script_failed"], g["script_flagged"], g["shift_checked"], g["shift_failed"], g["shift_flagged"],
            g["unspoken"]) == (3, 1, 0, 3, 1, 0, 1)
    assert any("has no sound" in x for x in job["stage_timings"]["_warnings"])
    assert tts.asked.count("refused") == 2                               # the stock voice and the language's other one
    v1mode.reload()


# ---------- the product rule that is always on in auto ----------
def test_in_auto_mode_a_live_session_without_a_streamer_profile_never_copies_the_voice_on_the_stream(auto, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.db import LocalStore
    from app.main import app
    store = LocalStore(tmp_path / "db.json")
    monkeypatch.setattr("app.live.routes.get_store", lambda: store)
    monkeypatch.setattr("app.live.session.get_store", lambda: store)
    body = {"target_langs": ["ta-IN"], "voice_from_stream": True, "voice_consent": True, "record": True}
    auto()
    c = TestClient(app)
    r = c.post("/api/live/sessions", json=body)
    assert r.status_code == 201 and r.json()["voice_from_stream"] is False       # stock voices, whatever the tick says
    assert store._db["live_sessions"][-1].get("record") is True                  # a recording is the session's own ask
    auto("live_stock_default: off\nlive_record: off\n")
    r = c.post("/api/live/sessions", json=body)
    assert r.status_code == 201 and r.json()["voice_from_stream"] is True
    assert not store._db["live_sessions"][-1].get("record")


def test_manual_mode_builds_nothing_of_auto_mode(monkeypatch, tmp_path):
    p, llm, gpu, store, sess = d.make(monkeypatch, tmp_path)
    assert not p._auto and not p._budget and p._meaning is None and not p._fallback and not p._script_guard
    assert p._merger is None and p._gates == {} and p._wps is None and p._ladder is None and p._en_mode is None
    assert p.dense_stats() == {} and json.dumps(p.warm_stats()) == "{}"


def test_an_overrides_file_saved_with_a_byte_order_mark_reads_the_same(auto):
    f = auto(None)
    f.write_text("# written by a script\nlive_budget: off\n", encoding="utf-8-sig")     # as PowerShell writes it
    v1mode.reload()
    assert v1mode.overrides() == {"live_budget": False}
