"""v1.1 Studio HQ: the judge per language, calibration, adaptive takes, the normaliser, glossary candidates and
the rubric review. Fake providers only; every flag is off unless a test switches it on."""
import json
import unicodedata
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import LocalStore
from app.providers.base import ProviderError, STTResult
from app.v1 import flags, qa
from app.v1.hq import calibrate, judge, normalise, review
from app.v1.hq import glossary as hqgloss
from app.v1.hq import runner as hq
from app.v1.hq import voice as hqvoice
from app.v1.stages import StageFailed, Stages
from tests.test_studio_pipeline import make_video
from tests.test_v1_hq import CLONE, VOICE, FakeStages, hq_settings, needs_ffmpeg, rig, tone  # noqa: F401 - fixtures

WS3_FLAGS = ("v1_hq_judge", "v1_hq_calibrate", "v1_hq_adaptive", "v1_hq_normalise", "v1_hq_auto_glossary", "v1_hq_review")
# The same Bengali words stored two ways: one code point per letter, and letter + dot.
BN_ONE = "হয় দিয়ে পড়ল"
BN_TWO = unicodedata.normalize("NFC", BN_ONE)


def test_every_new_flag_is_listed_and_off():
    s = get_settings()
    assert all(name in flags.FLAGS and getattr(s, name) is False for name in WS3_FLAGS)
    assert s.v1_hq_takes_fixed == 0 and s.v1_hq_adaptive_max == 5 and s.v1_hq_nbest == 4


# ---------- the judge ----------
class FakeRouter:
    """Only what `Stages.score` and the judge ask a router for."""

    def __init__(self, settings, stt: dict, have: tuple[str, ...] = ("prisma", "whisper_gpu")) -> None:
        self.s, self._stt, self._have = settings, stt, have

    def available(self, name):
        return name in self._have

    def chain(self, mode, engine, stage):
        return [n for n in {"score": ["qa_server", "prisma"]}.get(stage, []) if self.available(n)]

    def timeout(self, stage):
        return 5.0

    def provider(self, kind, name):
        return self._stt[name]


class Hears:
    def __init__(self, text: str | None) -> None:
        self.text, self.calls = text, 0

    async def transcribe(self, path, lang, **kw):
        self.calls += 1
        if self.text is None:
            raise ProviderError("the service is down")
        return STTResult(text=self.text)


def test_the_two_spellings_of_a_letter_are_one_word_only_under_the_new_rule():
    assert BN_ONE != BN_TWO
    assert qa.heard_share(BN_ONE, BN_TWO) == 0.0                              # v1's rule, unchanged
    assert qa.heard_share(BN_ONE, BN_TWO, qa.HEARD_RULE_NFC) == 1.0
    assert qa.heard_share("पढ़ाई ज़रूरी है", unicodedata.normalize("NFC", "पढ़ाई ज़रूरी है"), qa.HEARD_RULE_NFC) == 1.0
    assert qa.heard_share("நான் வந்தேன்", "நான் வந்‌தேன்", qa.HEARD_RULE_NFC) == 1.0   # an unseen joiner splits no word
    for said, heard in (("ek do teen", "ek do"), ("pi si aar test", "PCR test"), ("வணக்கம் நண்பா", "வணக்கம்")):
        assert qa.heard_share(said, heard, qa.HEARD_RULE_NFC) == qa.heard_share(said, heard)   # nothing else moved
    assert qa.rule_now() == qa.HEARD_RULE


async def test_judge_off_is_the_routing_list_and_the_old_rule(tmp_path):
    s = get_settings()
    prisma = Hears(BN_TWO)
    st = Stages("studio_hq", "gpu", router=FakeRouter(s, {"prisma": prisma}))
    got = await st.score(tmp_path / "a.wav", BN_ONE, "bn-IN")
    assert got["by"] == "prisma" and got["rule"] == qa.HEARD_RULE and got["backcheck"] == 0.0 and "passed_over" not in got
    assert st.judges("bn-IN") == ["prisma"]


async def test_judge_on_hears_with_the_first_judge_and_says_who(tmp_path, monkeypatch):
    s = get_settings().model_copy(update={"v1_hq_judge": True})
    prisma, whisper = Hears(BN_TWO), Hears("should not be asked")
    st = Stages("studio_hq", "gpu", router=FakeRouter(s, {"prisma": prisma, "whisper_gpu": whisper}))
    got = await st.score(tmp_path / "a.wav", BN_ONE, "bn-IN")
    assert got == {"heard": BN_TWO, "backcheck": 1.0, "similarity": None, "by": "prisma", "rule": qa.HEARD_RULE_NFC,
                   "passed_over": []}
    assert whisper.calls == 0 and st.judges("bn-IN") == ["prisma"] and st.judges("hi-IN") == ["prisma", "whisper_gpu"]


async def test_judge_falls_back_to_our_model_for_hindi_only(tmp_path, monkeypatch):
    s = get_settings().model_copy(update={"v1_hq_judge": True})

    class Local:
        async def to_devanagari(self, text):
            return {"namaste doston": "नमस्ते दोस्तों"}.get(text, text)
    monkeypatch.setattr("app.providers._local_llm", lambda: Local())
    st = Stages("studio_hq", "gpu", router=FakeRouter(s, {"prisma": Hears(None), "whisper_gpu": Hears("namaste doston")}))
    got = await st.score(tmp_path / "a.wav", "नमस्ते दोस्तों", "hi-IN")
    assert got["by"] == "whisper_gpu" and got["backcheck"] == 1.0 and got["passed_over"] == ["prisma"]
    with pytest.raises(StageFailed):                       # nobody else here hears Tamil: the line is "not checked"
        await st.score(tmp_path / "a.wav", "வணக்கம்", "ta-IN")
    # ... until the QA server's multilingual Whisper is there
    monkeypatch.setattr("app.v1.qa.QAClient.score", lambda self, wav, text, lang, ref=None: _heard("வணக்கம்"))
    st3 = Stages("studio_hq", "gpu", router=FakeRouter(s, {"prisma": Hears(None)}, have=("prisma", "qa_server")))
    got = await st3.score(tmp_path / "a.wav", "வணக்கம்", "ta-IN")
    assert got["by"] == "qa_server" and got["backcheck"] == 1.0 and got["passed_over"] == ["prisma"]
    # a transcript our model could not put into Devanagari is no judgement
    st2 = Stages("studio_hq", "gpu", router=FakeRouter(s, {"prisma": Hears(None), "whisper_gpu": Hears("kuch aur")}))
    with pytest.raises(StageFailed):
        await st2.score(tmp_path / "a.wav", "नमस्ते दोस्तों", "hi-IN")


async def _heard(text):
    return {"heard": text, "backcheck": 1.0, "similarity": None}


def test_judge_order_per_language():
    s = get_settings().model_copy(update={"v1_hq_judge_by_lang": "hi-IN=whisper_gpu,prisma;ta-IN=whisper_gpu"})
    assert judge.order(s, "hi-IN") == ["whisper_gpu", "prisma"]
    assert judge.order(s, "ta-IN") == []                    # our model does not hear Tamil, whatever the file says
    assert judge.order(s, "bn-IN") == ["prisma", "qa_server"]
    assert judge.order(get_settings(), "hi-IN") == ["prisma", "whisper_gpu", "qa_server"]
    assert judge.order(get_settings(), "ta-IN") == ["prisma", "qa_server"]     # the QA server's Whisper hears every language


async def test_a_stored_hearing_is_scored_again_under_the_rule_in_use(hq_settings, monkeypatch):
    class OldScore(FakeStages):
        async def score(self, wav, text, lang, ref_wav=None):
            return {"heard": BN_TWO, "backcheck": 0.0, "similarity": None, "by": "prisma", "rule": qa.HEARD_RULE}
    best, made, flagged = await hqvoice.best_line(OldScore(hq_settings), BN_ONE, "bn-IN", VOICE, 3.0, None, hq_settings, {})
    assert best.backcheck == 0.0 and flagged and "rule" not in best.public() and "heard" not in best.public()
    monkeypatch.setattr(hq_settings, "v1_hq_judge", True)
    best, made, flagged = await hqvoice.best_line(OldScore(hq_settings), BN_ONE, "bn-IN", VOICE, 3.0, None, hq_settings, {})
    assert best.backcheck == 1.0 and not flagged            # from the cache: heard once, counted by the new rule
    assert best.public(heard=True)["rule"] == qa.HEARD_RULE_NFC and best.public(heard=True)["heard"] == BN_TWO


# ---------- adaptive takes ----------
def test_take_plan():
    s = get_settings()
    assert hqvoice.take_plan(s) == (4, None, False)
    assert hqvoice.take_plan(s.model_copy(update={"v1_hq_adaptive": True})) == (5, 0.9, False)
    assert hqvoice.take_plan(s.model_copy(update={"v1_hq_adaptive": True, "v1_hq_adaptive_min": 0.8})) == (5, 0.8, False)
    assert hqvoice.take_plan(s.model_copy(update={"v1_hq_adaptive": True, "v1_hq_takes_fixed": 3})) == (3, None, True)


async def test_adaptive_makes_one_take_when_it_is_good_and_up_to_five_when_not(hq_settings, monkeypatch):
    monkeypatch.setattr(hq_settings, "v1_hq_adaptive", True)
    st = FakeStages(hq_settings, own=True, checks=[0.92])
    best, made, flagged = await hqvoice.best_line(st, "adaptive one two three", "ta-IN", CLONE, 3.0, None, hq_settings, {})
    assert len(made) == 1 and not flagged
    assert hq_settings.v1_hq_adaptive_same_stop is False                  # off unless asked for
    st = FakeStages(hq_settings, own=True, checks=[0.5, 0.6, 0.7, 0.8, 0.85, 0.99])
    best, made, flagged = await hqvoice.best_line(st, "adaptive four five six", "ta-IN", CLONE, 3.0, None, hq_settings, {})
    assert len(made) == 5 and best.backcheck == 0.85 and flagged          # five, never six
    st = FakeStages(hq_settings, own=True, checks=[0.5, 0.95, 1.0])
    best, made, flagged = await hqvoice.best_line(st, "adaptive seven eight nine", "ta-IN", CLONE, 3.0, None, hq_settings, {})
    assert len(made) == 2 and best.backcheck == 0.95                      # stops at the first take over the threshold
    # its own threshold: a take over it stops the takes, the flag keeps its own line
    monkeypatch.setattr(hq_settings, "v1_hq_adaptive_min", 0.8)
    st = FakeStages(hq_settings, own=True, checks=[0.85, 1.0])
    best, made, flagged = await hqvoice.best_line(st, "adaptive ten eleven twelve", "ta-IN", CLONE, 3.0, None, hq_settings, {})
    assert len(made) == 1 and flagged


async def test_adaptive_stops_when_two_takes_are_heard_as_the_same_words(hq_settings, monkeypatch):
    monkeypatch.setattr(hq_settings, "v1_hq_adaptive", True)
    monkeypatch.setattr(hq_settings, "v1_hq_adaptive_same_stop", True)

    class SameEar(FakeStages):
        async def score(self, wav, text, lang, ref_wav=None):
            return {"heard": "same words every time", "backcheck": 0.75, "similarity": None, "by": "prisma", "rule": qa.HEARD_RULE}
    st = SameEar(hq_settings, own=True)
    best, made, flagged = await hqvoice.best_line(st, "same words every tyme", "ta-IN", CLONE, 3.0, None, hq_settings, {})
    assert len(made) == 2 and flagged                                     # the third take would be heard the same way
    monkeypatch.setattr(hq_settings, "v1_hq_adaptive_same_stop", False)
    st = SameEar(hq_settings, own=True)
    best, made, flagged = await hqvoice.best_line(st, "same words every tyme again", "ta-IN", CLONE, 3.0, None, hq_settings, {})
    assert len(made) == 5
    monkeypatch.setattr(hq_settings, "v1_hq_adaptive", False)             # v1's own rule never looks at what was heard
    st = SameEar(hq_settings, own=True)
    best, made, flagged = await hqvoice.best_line(st, "same words every tyme once more", "ta-IN", CLONE, 3.0, None, hq_settings, {})
    assert len(made) == hq_settings.v1_hq_nbest


async def test_fixed_takes_makes_every_take_and_keeps_the_best(hq_settings, monkeypatch):
    monkeypatch.setattr(hq_settings, "v1_hq_takes_fixed", 5)
    st = FakeStages(hq_settings, own=True, checks=[1.0, 0.4, 0.9, 1.0, 0.7])
    best, made, flagged = await hqvoice.best_line(st, "fixed one two three", "ta-IN", CLONE, 3.0, None, hq_settings, {})
    assert len(made) == 5 and best.backcheck == 1.0 and not flagged
    st = FakeStages(hq_settings, own=False, checks=[0.5])                  # a stock voice says the same thing each time
    best, made, flagged = await hqvoice.best_line(st, "fixed four five six", "ta-IN", VOICE, 3.0, None, hq_settings, {})
    assert len(made) == 1


# ---------- the normaliser ----------
NUMBERS = {
    "hi-IN": {0: "शून्य", 7: "सात", 19: "उन्नीस", 25: "पच्चीस", 49: "उनचास", 68: "अड़सठ", 99: "निन्यानवे", 100: "एक सौ",
              250: "दो सौ पचास", 1000: "एक हज़ार", 2026: "दो हज़ार छब्बीस", 150000: "एक लाख पचास हज़ार",
              25000000: "दो करोड़ पचास लाख"},
    "bn-IN": {0: "শূন্য", 7: "সাত", 19: "উনিশ", 25: "পঁচিশ", 49: "ঊনপঞ্চাশ", 68: "আটষট্টি", 99: "নিরানব্বই", 100: "একশো",
              250: "দুইশো পঞ্চাশ", 1000: "এক হাজার", 2026: "দুই হাজার ছাব্বিশ", 150000: "এক লক্ষ পঞ্চাশ হাজার",
              25000000: "দুই কোটি পঞ্চাশ লক্ষ"},
    "ta-IN": {0: "பூஜ்ஜியம்", 7: "ஏழு", 19: "பத்தொன்பது", 25: "இருபத்து ஐந்து", 49: "நாற்பத்து ஒன்பது", 68: "அறுபத்து எட்டு",
              99: "தொண்ணூற்று ஒன்பது", 100: "நூறு", 250: "இருநூற்று ஐம்பது", 1000: "ஆயிரம்",
              2026: "இரண்டாயிரத்து இருபத்து ஆறு", 150000: "ஒரு லட்சத்து ஐம்பது ஆயிரம்", 25000000: "இரண்டு கோடியே ஐம்பது லட்சம்"},
    "en-IN": {0: "zero", 7: "seven", 19: "nineteen", 25: "twenty-five", 49: "forty-nine", 68: "sixty-eight",
              99: "ninety-nine", 100: "one hundred", 250: "two hundred fifty", 1000: "one thousand",
              2026: "two thousand twenty-six", 150000: "one lakh fifty thousand", 25000000: "two crore fifty lakh"},
}
LINES = {
    "hi-IN": [("₹500 दे दो", "पाँच सौ रुपये दे दो"), ("45% लोग", "पैंतालीस प्रतिशत लोग"), ("2.5 kg आटा", "दो दशमलव पाँच किलो आटा"),
              ("15/08/1947 को", "पंद्रह अगस्त उन्नीस सौ सैंतालीस को"), ("9:30 पर आना", "नौ बजकर तीस मिनट पर आना"),
              ("Rs. 2.5 lakh लगे", "दो दशमलव पाँच लाख रुपये लगे"), ("Dr. राव आए", "डॉक्टर राव आए"),
              ("१२ बच्चे", "बारह बच्चे"), ("10-12 लोग", "दस से बारह लोग"), ("1,50,000 views", "एक लाख पचास हज़ार views")],
    "bn-IN": [("₹500 দাও", "পাঁচশো টাকা দাও"), ("45% মানুষ", "পঁয়তাল্লিশ শতাংশ মানুষ"), ("2.5 kg আটা", "দুই দশমিক পাঁচ কেজি আটা"),
              ("15/08/1947 সালে", "পনেরো আগস্ট উনিশশো সাতচল্লিশ সালে"), ("9:30 এ এসো", "নয়টা ত্রিশ এ এসো"),
              ("Rs. 2.5 lakh লাগল", "দুই দশমিক পাঁচ লক্ষ টাকা লাগল"), ("Dr. রায় এলেন", "ডাক্তার রায় এলেন"),
              ("১২ জন", "বারো জন"), ("10-12 জন", "দশ থেকে বারো জন")],
    "ta-IN": [("₹500 கொடு", "ஐநூறு ரூபாய் கொடு"), ("45% பேர்", "நாற்பத்து ஐந்து சதவீதம் பேர்"), ("2.5 kg மாவு", "இரண்டு புள்ளி ஐந்து கிலோ மாவு"),
              ("15/08/1947 அன்று", "பதினைந்து ஆகஸ்ட் ஆயிரத்து தொள்ளாயிரத்து நாற்பத்து ஏழு அன்று"),
              ("9:30 க்கு வா", "ஒன்பது மணி முப்பது நிமிடம் க்கு வா"), ("Rs. 2.5 lakh ஆனது", "இரண்டு புள்ளி ஐந்து லட்சம் ரூபாய் ஆனது"),
              ("Dr. ராவ் வந்தார்", "டாக்டர் ராவ் வந்தார்"), ("௧௨ பேர்", "பன்னிரண்டு பேர்"), ("10-12 பேர்", "பத்து முதல் பன்னிரண்டு பேர்")],
    "en-IN": [("Pay ₹500 now", "Pay five hundred rupees now"), ("45% of people", "forty-five percent of people"),
              ("2.5 kg of flour", "two point five kilos of flour"), ("on 15/08/1947", "on fifteen August nineteen hundred forty-seven"),
              ("come at 9:30", "come at nine thirty"), ("come at 9:05", "come at nine oh five"), ("it cost Rs. 2.5 lakh", "it cost two point five lakh rupees"),
              ("Dr. Rao came", "Doctor Rao came"), ("10-12 people", "ten to twelve people"), ("$20 each", "twenty dollars each")],
}


@pytest.mark.parametrize("lang", sorted(normalise.COVERED))
def test_number_words(lang):
    for n, words in NUMBERS[lang].items():
        assert normalise.number_words(n, lang) == words, (lang, n)
    with pytest.raises(ValueError):
        normalise.number_words(10**9, lang)


@pytest.mark.parametrize("lang", sorted(normalise.COVERED))
def test_lines_are_written_out(lang):
    for line, want in LINES[lang]:
        assert normalise.spoken(line, lang) == want, (lang, line)
    plain = LINES[lang][0][1]
    assert normalise.spoken(plain, lang) == plain                       # nothing to write out: untouched
    from app.v1.hq.text import UNSPOKEN
    assert not any(UNSPOKEN.search(normalise.spoken(line, lang)) for line, _ in LINES[lang])


def test_every_table_is_whole_and_without_repeats():
    for name, table in (("hi", normalise.HI), ("bn", normalise.BN)):
        assert len(table) == 100 and len(set(table)) == 100, name
    assert all(len(v) == 12 for v in normalise.MONTHS.values()) and all(len(v) == 26 for v in normalise.LETTERS.values())
    for lang in normalise.COVERED:                                       # every number up to a lakh has words, all different
        seen = {normalise.number_words(n, lang) for n in range(0, 100000, 7)}
        assert len(seen) == len(range(0, 100000, 7)), lang


def test_abbreviations_are_spelled_for_our_voice_only_and_other_languages_are_left():
    assert normalise.spoken("PCR டெஸ்ட்", "ta-IN", native=True) == "பி சி ஆர் டெஸ்ட்"
    assert normalise.spoken("DNA परीक्षण", "hi-IN", native=True) == "डी एन ए परीक्षण"
    assert normalise.spoken("GST বাড়ল", "bn-IN", native=True) == "জি এস টি বাড়ল"
    assert normalise.spoken("PCR டெஸ்ட்", "ta-IN", native=False) == "PCR டெஸ்ட்"      # a stock voice reads Latin letters
    assert not normalise.covered("te-IN") and normalise.spoken("₹500 ఇవ్వు", "te-IN") == "₹500 ఇవ్వు"
    for lang in ("te-IN", "kn-IN", "ml-IN", "mr-IN", "gu-IN", "pa-IN"):
        assert not normalise.covered(lang)
    assert normalise.spoken_lines(["₹5 दो", "ठीक है"], "hi-IN") == (["पाँच रुपये दो", "ठीक है"], 1)
    assert normalise.spoken("9876543210 पर call करो", "hi-IN").startswith("नौ आठ सात छह")   # a phone number: digit by digit


# ---------- glossary candidates ----------
def test_glossary_candidates_from_a_hindi_transcript():
    lines = ["दोस्तों, आज हम Valorant खेलेंगे और मैं jet लूँगा।", "BGMI में loot बहुत है।", "oxygen की कमी से problem होती है।",
             "hemoglobin RBC में होता है और oxygen को carry करता है।", "Sensex गिरा और Nifty भी नीचे बंद हुआ।",
             "Edward Jenner ने vaccine बनाई।", "Edward Jenner को याद रखो, vaccine important है।", "YouTube पर video डालो।",
             "T20 match है।", "हेमोग्लोबिन ज़रूरी है", "हेमोग्लोबिन कम है", "हेमोग्लोबिन बढ़ाओ"]
    got = hqgloss.candidates(lines)
    by = {c["term"]: c for c in got}
    for name in ("Valorant", "Sensex", "Nifty", "Edward Jenner", "YouTube"):
        assert by[name]["kind"] == "name", name
    for short in ("BGMI", "RBC", "T20"):
        assert by[short]["kind"] == "short", short
    assert by["oxygen"] == {"term": "oxygen", "kind": "term", "lines": 2} and by["vaccine"]["lines"] == 2
    assert "jet" not in by and "loot" not in by and "Edward" not in by and "Jenner" not in by   # said once / part of a name
    assert by["हेमोग्लोबिन"]["kind"] == "repeat"
    kinds = [c["kind"] for c in got]
    assert kinds == sorted(kinds, key=lambda k: {"name": 0, "short": 0, "term": 1, "repeat": 2}[k])
    assert "हेमोग्लोबिन" not in hqgloss.terms(got) and "Valorant" in hqgloss.terms(got)
    assert "Valorant" not in {c["term"] for c in hqgloss.candidates(lines, known=["valorant"])}
    assert len(hqgloss.candidates(lines, limit=3)) == 3 and hqgloss.candidates([]) == []


def test_glossary_candidates_from_a_latin_transcript():
    lines = ["Doston, aaj hum Valorant khelenge aur main Jet loonga.", "BGMI mein loot bahut hai.", "Aaj Valorant mein maza aayega."]
    by = {c["term"]: c for c in hqgloss.candidates(lines)}
    assert set(by) == {"Valorant", "Jet", "BGMI"}                        # no "term": every word is in Latin letters
    assert "Doston" not in by and "Aaj" not in by                        # the first word of a line is no name by itself


# ---------- the rubric review ----------
class ReviewStages(FakeStages):
    """FakeStages with the pieces the rubric review asks for: a hosted model called through the provider walk."""

    def __init__(self, settings, answer, have=("gemini",), **kw):
        super().__init__(settings, **kw)
        self.answer, self.asked = answer, []
        outer = self

        class Gemini:
            async def _chat(self, system, user, **k):
                outer.asked.append((system, json.loads(user)))
                return outer.answer if isinstance(outer.answer, str) else json.dumps(outer.answer, ensure_ascii=False)
        self.r.available = lambda name: name in have
        self.r.provider = lambda kind, name: Gemini()

    async def _run(self, stage, names, call, timeout=None):
        self.ran = (stage, list(names))
        out = await call(names[0])
        self.used[stage] = names[0]
        return out


async def test_review_edits_only_what_fails_and_logs_every_edit(hq_settings, monkeypatch, tmp_path):
    monkeypatch.setattr(hq_settings, "v1_trace", True)
    src = ["aaj 500 log aaye", "phir milte hain", "bahut lamba vakya hai yeh", "naam Ravi hai"]
    dub = ["இன்று ஐம்பது பேர் வந்தார்கள்", "மீண்டும் சந்திப்போம்", "இது மிக நீண்ட வாக்கியம்", "பெயர் ரவி"]
    answer = [{"ok": False, "rule": "numbers_names", "text": "இன்று ஐநூறு பேர் வந்தார்கள்", "note": "50 for 500"},
              {"ok": True},
              {"ok": False, "rule": "length", "text": "ஒன்று இரண்டு மூன்று நான்கு ஐந்து ஆறு ஏழு எட்டு ஒன்பது", "note": "too long"},
              {"ok": False, "rule": "register", "text": "name is Ravi", "note": "wrong script"}]
    st = ReviewStages(hq_settings, answer)
    out, stats = await review.review(st, src, dub, [5, 5, 4, 5], "ta-IN", ["Ravi"], native=True,
                                     heard=["aaj 500 log aaye", "फिर मिलते हैं", src[2], src[3]], job_id="job-1")
    assert out == [answer[0]["text"], dub[1], dub[2], dub[3]]            # one edit taken, two refused, one line fine
    assert stats["edited"] == 1 and stats["rejected"] == 2 and stats["by_rule"] == {"numbers_names": 1} and stats["model"] == "gemini"
    system, items = st.asked[0]
    assert st.ran == ("review", ["gemini"]) and "MEANING KEPT" in system and "FITS THE SLOT" in system and "Ravi" in system
    assert "heard" not in items[0] and items[1]["heard"] == "फिर मिलते हैं"   # only where the first hearing differs
    data = Path(hq_settings.data_dir)
    words = [json.loads(x) for x in (data / "hq_review" / "job-1.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [w["taken"] for w in words] == [True, False, False] and words[0]["before"] == dub[0] and words[0]["note"] == "50 for 500"
    assert [w["rejected_why"] for w in words] == [None, "over the word limit", "wrong script"]
    traced = [json.loads(x) for f in (data / "trace").glob("*.jsonl") for x in f.read_text(encoding="utf-8").splitlines()]
    edits = [t for t in traced if t["kind"] == "hq_review_edit"]
    assert len(edits) == 3 and edits[0]["rule"] == "numbers_names" and edits[0]["before_words"] == 4 and edits[0]["after_chars"] == len(answer[0]["text"])
    blob = json.dumps(edits, ensure_ascii=False)
    assert not any(text in blob for text in (*src, *dub, "50 for 500", answer[0]["text"]))   # sizes and reasons, never the words


async def test_review_asks_again_for_a_line_it_failed_without_a_correction(hq_settings):
    class TwoStep(ReviewStages):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            outer = self

            class Gemini:
                async def _chat(self, system, user, **kw):
                    outer.asked.append((system, json.loads(user)))
                    if "failed_rule" in user:
                        return json.dumps(["தடுப்பூசியை உருவாக்கினார்"], ensure_ascii=False)
                    return json.dumps([{"ok": False, "rule": "meaning", "note": "made, not gave"}, {"ok": True}])
            self.r.provider = lambda kind, name: Gemini()
    st = TwoStep(hq_settings, None)
    out, stats = await review.review(st, ["vaccine banaya", "theek hai"], ["தடுப்பூசி போட்டார்", "சரி"], [4, 4], "ta-IN", [], native=True, job_id="job-3")
    assert out == ["தடுப்பூசியை உருவாக்கினார்", "சரி"] and stats["edited"] == 1 and stats["asked_again"] == 1
    assert len(st.asked) == 2 and st.asked[1][1] == [{"source": "vaccine banaya", "dub": "தடுப்பூசி போட்டார்", "max_words": 4,
                                                      "failed_rule": "meaning", "what_is_wrong": "made, not gave"}]


async def test_review_that_cannot_be_used_changes_nothing(hq_settings):
    st = ReviewStages(hq_settings, "sorry, no JSON today")
    out, stats = await review.review(st, ["a b"], ["அ ஆ"], [4], "ta-IN", [], native=True, job_id="job-2")
    assert out == ["அ ஆ"] and stats["edited"] == 0 and "error" in stats
    st = ReviewStages(hq_settings, [{"ok": True}], have=())                # no hosted model: the routing file's review list
    await review.review(st, ["a b"], ["அ ஆ"], [4], "ta-IN", [], native=True)
    assert st.ran == ("review", ["gemma"])


def test_a_cleaned_line_must_still_be_the_line_that_was_heard():
    keeps = review.keeps_source
    assert keeps("oxygen की कमी से, सांस लेने में problem हो जाती है", "oxygen की कमी से सांस लेने में problem हो जाती है।")   # punctuation
    assert keeps("लुई Pastor ने rabies का vaccine बनाया था।", "लुई Pasteur ने rabies का vaccine बनाया था।")          # a name respelled
    assert keeps("option B को lock कर दो, बिल्कुल सही जवाब है।", "Option B को lock कर दो, बिल्कुल सही जवाब है।")
    assert keeps("अं मतलब मतलब आज हम game खेलेंगे", "मतलब आज हम game खेलेंगे")                                        # a filler and a stammer gone
    assert keeps("um aaj hum khelenge", "aaj hum khelenge")
    # each of these came out of the merge or the clean step of a real job
    assert not keeps("oxygen की कमी से सांस लेने में problem हो जाती है।", "Ki kami se saans lene mein problem ho jaati hai.")
    assert not keeps("hemoglobin RBC में होता है और oxygen को carry करता है।", "Hemoglobin RBC mein hota hai aur oxygen ko carry karta hai.")
    assert not keeps("hemoglobin RBC में होता है और oxygen को carry करता है।", "RBC में होता है और oxygen को carry करता है।")
    assert not keeps("Mitochondria को cell का power house कहा जाता है।", "को cell का power house कहा जाता है।")
    assert not keeps("neutrophil और macrophage phagocytosis करते हैं।", "Aur macrophage phagocytosis karte hain।")
    assert not keeps("जल्दी से chat में बताओ।", "Main batao.")
    assert not keeps("इसका answer सही है।", "सा answer सही है?")
    assert not keeps("BGMI में poaching की उतरते हैं, वहाँ loot बहुत है।", "BGMI में पूछहinki उतराते हैं, वहां loot बहुत है।")
    # every line holding the line before it
    assert not keeps("Mitochondria को cell का power house कहा जाता है।", "neutrophil और macrophage phagocytosis करते हैं।")
    assert not keeps("जल्दी से chat में बताओ सब लोग अभी", "बताओ") and not keeps("कुछ भी", "")


# ---------- the flags in a whole job ----------
class ScriptedStages(ReviewStages):
    async def chat(self, system, user, *, stage="translate", max_tokens=3000, temperature=0.2):
        if "`max_words`: how many" in system:
            self.translate_system = system
            return json.dumps(["விலை ₹500" for _ in json.loads(user)], ensure_ascii=False)
        if "Clean each line" in system:
            self.clean_system = system
            return json.dumps(["bilkul alag line Latin mein" for _ in json.loads(user)])
        return await super().chat(system, user, stage=stage, max_tokens=max_tokens, temperature=temperature)


@needs_ffmpeg
async def test_hq_job_with_the_text_flags_on(rig):  # noqa: F811
    r, tmp, made, stages, monkeypatch = rig
    r.s = r.s.model_copy(update={"v1_hq_review": True, "v1_hq_normalise": True, "v1_hq_auto_glossary": True,
                                 "v1_hq_judge": True, "v1_hq_adaptive": True})

    class NamedSTT:
        async def transcribe(self, wav_path, lang="indic-auto", **kw):
            return STTResult(text="आज Valorant खेलेंगे BGMI नहीं", detected_lang="hi-IN")
    r._stt = NamedSTT()

    def scripted(job_id, engine):
        made.append(ScriptedStages(r.s, [{"ok": True}] * 3, checks=[1.0] * 9))
        return made[-1]
    monkeypatch.setattr(hq, "stages_for", scripted)
    job = await r.create_job(make_video(tmp / "u.mp4"), "reel.mp4", ["ta-IN"], quality="hq")
    await r.run(job["id"])
    job = await r.store.get("jobs", job["id"])
    assert job["status"] == "done", job.get("error")
    st = made[0]
    meta = json.loads((r.job_dir(job["id"]) / "meta.json").read_text(encoding="utf-8"))
    assert {c["term"] for c in meta["hq"]["glossary_auto"]} == {"Valorant", "BGMI"}
    assert "Valorant" in st.clean_system and "Names and terms of this video" in st.translate_system and "BGMI" in st.translate_system
    assert meta["hq"]["transcript_put_back"] == 3                       # the "cleaned" lines were not the lines heard
    segs = await r.spoken_segments(job["id"])
    assert all(s["src_text"] == "आज Valorant खेलेंगे BGMI नहीं" for s in segs)
    trs = [(await r.store.select("translations", segment_id=s["id"], lang="ta-IN"))[0] for s in segs]
    assert all(t["text"] == "விலை ஐநூறு ரூபாய்" for t in trs)             # by rule, before any voice saw the line
    assert meta["hq"]["text:ta-IN"]["normalised_by_rule"] == 3 and meta["hq"]["text:ta-IN"]["review"]["asked"] == 3
    assert not any(c.startswith("review") for c in st.chats)            # the rubric review replaced the plain one
    assert all(len(t["alts"]) == 1 and t["alts"][0]["rule"] == qa.HEARD_RULE_NFC and "heard" in t["alts"][0] for t in trs)
    usage = (await r.store.get("jobs", job["id"]))["stage_timings"]["_usage"]
    assert usage["tts_calls"] + usage.get("tts_cache_hits", 0) == 3       # one take a line, no more


@needs_ffmpeg
async def test_hq_job_with_the_new_flags_off_is_as_before(rig):  # noqa: F811
    r, tmp, made, stages, monkeypatch = rig
    assert not any(getattr(r.s, f) for f in WS3_FLAGS)
    monkeypatch.setattr(hq, "stages_for", lambda job_id, engine: stages(job_id, engine, own=True, checks=[1.0, 0.3, 0.4, 0.95, 1.0]))
    job = await r.create_job(make_video(tmp / "u.mp4"), "reel.mp4", ["ta-IN"], quality="hq")
    await r.run(job["id"])
    st = made[0]
    assert [c.split(":")[0] for c in st.chats] == ["translate", "translate", "review", "translate"]   # clean, translate, review, numbers
    meta = json.loads((r.job_dir(job["id"]) / "meta.json").read_text(encoding="utf-8"))
    assert "glossary_auto" not in meta["hq"] and "transcript_put_back" not in meta["hq"]
    assert set(meta["hq"]["text:ta-IN"]) == {"reviewed_changed", "normalised", "over_limit"}
    assert not (Path(r.s.data_dir) / "hq_review").exists() and not (Path(r.s.data_dir) / "calibration").exists()
    segs = await r.spoken_segments(job["id"])
    trs = [(await r.store.select("translations", segment_id=s["id"], lang="ta-IN"))[0] for s in segs]
    keys = {k for t in trs for a in t["alts"] for k in a}
    assert keys == {"idx", "path", "provider", "text", "engine_speed", "dur_s", "speed", "backcheck", "similarity",
                    "scored_by", "passed", "why", "gpu_ms"}             # a stored take has the fields it always had
    assert len(trs[1]["alts"]) == 3 and set(trs[1]["qa"]) == {"backcheck", "similarity", "by", "provider"}


# ---------- calibration ----------
@pytest.fixture
def cal(tmp_path, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "data_dir", str(tmp_path / "data"))
    monkeypatch.setattr(s, "v1_hq_calibrate", True)
    store = LocalStore(tmp_path / "db.json")
    return s, store, tmp_path


async def _takes(store, tmp_path, s, scores, lang="ta-IN", heard=None):
    d = Path(s.data_dir) / "cache" / "voice_hq"
    d.mkdir(parents=True, exist_ok=True)
    seg = await store.insert("segments", {"job_id": "job-1", "idx": 0, "start_s": 0, "end_s": 1, "src_text": "x"})
    alts = []
    for i, score in enumerate(scores):
        p = d / f"{lang}-{len(list(d.iterdir()))}.wav"
        p.write_bytes(tone(0.2))
        alts.append({"idx": i, "path": str(p), "text": f"line {lang} {i}", "backcheck": score, "scored_by": "prisma",
                     "provider": "indicf5", **({"heard": heard, "rule": qa.HEARD_RULE} if heard is not None else {})})
    await store.insert("translations", {"segment_id": seg["id"], "lang": lang, "text": "t", "alts": alts, "picked": 0})
    return alts


async def test_calibration_with_no_labels_says_so(cal):
    s, store, tmp = cal
    await _takes(store, tmp, s, [0.5, 0.8, 0.9, 1.0])
    got = await calibrate.summary(store)
    assert got["note"] == "no labels yet" and got["labelled"] == 0 and got["takes"] == 4
    assert got["recommended"] == {"threshold": None, "why": "no labels yet"} and got["at_threshold_in_use"] is None


async def test_calibration_queue_is_blind_and_covers_the_score_range(cal):
    s, store, tmp = cal
    await _takes(store, tmp, s, [0.5, 0.55, 0.6, 0.75, 0.9, 0.92, 1.0, 1.0, 1.0, 1.0, 1.0, None])
    its = await calibrate.items(store)
    assert len(its) == 11                                                # a take nobody scored is no item
    q = calibrate.queue(its, set(), n=4)
    assert sorted(sum(1 for b in calibrate.BANDS if i["score"] >= b) for i in q) == [0, 1, 2, 3]   # one from each band
    assert [i["id"] for i in q] == sorted(i["id"] for i in q)            # handed out in an order that says nothing
    assert all(set(calibrate.blind(i)) == {"id", "lang", "text"} for i in q)
    assert calibrate.queue(its, {i["id"] for i in its}) == [] and calibrate.queue(its, set(), lang="bn-IN") == []


async def test_calibration_agreement_and_recommendation(cal, monkeypatch):
    s, store, tmp = cal
    scores = [0.5, 0.6, 0.7, 0.75, 0.78, 0.8, 0.82, 0.85, 0.9, 0.95, 1.0, 1.0]
    await _takes(store, tmp, s, scores)
    its = sorted(await calibrate.items(store), key=lambda i: i["score"])
    for i in its[:4]:
        calibrate.add_label(i, "bad")
    got = await calibrate.summary(store)
    assert got["labelled"] == 4 and got["recommended"]["threshold"] is None and "not enough labels" in got["recommended"]["why"]
    monkeypatch.setattr(s, "v1_hq_calibrate_min_labels", 12)
    for i in its[4:]:                                                    # a person hears everything from 0.78 up as fine
        calibrate.add_label(i, "good")
    calibrate.add_label(its[4], "bad")                                   # ... and changes their mind about one
    got = await calibrate.summary(store)
    assert (got["good"], got["bad"], got["used"]) == (7, 5, 12)
    now = got["at_threshold_in_use"]                                     # 0.9: flags 0.8, 0.82, 0.85 although they were fine
    assert (now["flagged_bad"], now["flagged_good"], now["passed_bad"], now["passed_good"]) == (5, 3, 0, 4)
    assert now["agreement_pct"] == 75.0
    rec = got["recommended"]
    assert rec["threshold"] == 0.79 and rec["agreement_pct"] == 100.0 and rec["flagged_good"] == 0 and rec["passed_bad"] == 0
    assert got["by_lang"]["ta-IN"]["labels"] == 12
    calibrate.add_label(its[4], "undo")
    assert (await calibrate.summary(store))["labelled"] == 11


async def test_calibration_scores_a_stored_hearing_under_the_rule_in_use(cal, monkeypatch):
    s, store, tmp = cal
    alts = await _takes(store, tmp, s, [0.0], lang="bn-IN", heard=BN_TWO)
    seg = (await store.select("segments"))[0]
    tr = (await store.select("translations"))[0]
    await store.update("translations", tr["id"], {"alts": [{**alts[0], "text": BN_ONE}]})
    assert (await calibrate.items(store))[0]["score"] == 0.0             # the judge flag is off: the stored score
    monkeypatch.setattr(s, "v1_hq_judge", True)
    item = (await calibrate.items(store))[0]
    assert item["score"] == 1.0 and item["rule"] == qa.HEARD_RULE_NFC and seg["job_id"] == item["job"]
    # a label on a take scored under another rule is not mixed in
    monkeypatch.setattr(s, "v1_hq_judge", False)
    calibrate.add_label((await calibrate.items(store))[0], "good")
    await store.update("translations", tr["id"], {"alts": [{k: v for k, v in alts[0].items() if k not in ("heard", "rule")}]})
    monkeypatch.setattr(s, "v1_hq_judge", True)
    got = await calibrate.summary(store)
    assert got["used"] == 0 and got["left_out_other_rule"] == 1


def test_calibration_and_glossary_routes_answer_only_with_their_flags(cal, monkeypatch):
    s, store, tmp = cal
    from app.main import app
    from app.studio.routes import runner as live_runner
    monkeypatch.setattr(live_runner, "_store", store)
    c = TestClient(app)
    monkeypatch.setattr(s, "v1_hq_calibrate", False)
    for path in ("/api/v1/calibrate/next", "/api/v1/calibrate/summary", "/api/v1/calibrate/audio/x"):
        assert c.get(path).status_code == 404
    assert c.post("/api/v1/calibrate/labels", json={"id": "x", "label": "good"}).status_code == 404
    assert c.get("/api/v1/jobs/nope/glossary-candidates").status_code == 404
    assert not (Path(s.data_dir) / "calibration").exists()
    monkeypatch.setattr(s, "v1_hq_calibrate", True)
    import asyncio
    asyncio.run(_takes(store, tmp, s, [0.5, 1.0]))
    nxt = c.get("/api/v1/calibrate/next").json()
    assert nxt["takes"] == 2 and nxt["labelled"] == 0 and all(set(i) == {"id", "lang", "text"} for i in nxt["items"])
    first = nxt["items"][0]["id"]
    audio = c.get(f"/api/v1/calibrate/audio/{first}")
    assert audio.status_code == 200 and audio.headers["content-type"] == "audio/wav"
    assert c.post("/api/v1/calibrate/labels", json={"id": first, "label": "fine"}).status_code == 400
    assert c.post("/api/v1/calibrate/labels", json={"id": "nope", "label": "good"}).status_code == 404
    assert c.post("/api/v1/calibrate/labels", json={"id": first, "label": "bad"}).json() == {"ok": True, "labelled": 1}
    summ = c.get("/api/v1/calibrate/summary").json()
    assert summ["labelled"] == 1 and summ["recommended"]["threshold"] is None
    assert "score" not in json.dumps(c.get("/api/v1/calibrate/next").json())
    assert (Path(s.data_dir) / "calibration" / "labels.jsonl").exists()
