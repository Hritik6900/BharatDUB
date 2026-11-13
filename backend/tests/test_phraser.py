"""Phrases cut from Prisma partials (live chunking before the speaker pauses)."""
from app.live.assembler import PARTIAL_LAG_MS, Phraser
from app.providers.stt_gnani import parse_ws_message


def test_waits_for_enough_stable_words():
    p = Phraser(min_words=4, max_words=8)
    assert p.partial("u1", "कहीं भी", "कहीं भी तंदूरी खाओगे", 1000) is None
    assert not p.covered("u1")


def test_cuts_before_a_word_that_opens_the_next_clause():
    p = Phraser(min_words=4, max_words=8)
    p.partial("u1", "", "उसी oil को बार", 1000)
    cut = p.partial("u1", "उसी oil को बार बार बदलते रहते हैं और", "उसी oil को बार बार बदलते रहते हैं और पकाते", 2000)
    assert cut is not None
    text, t_start, t_end = cut
    assert text == "उसी oil को बार बार बदलते रहते हैं"   # ends on "हैं", the next word is "और"
    assert t_start == 1000 - PARTIAL_LAG_MS and t_end == 2000 - PARTIAL_LAG_MS
    assert p.covered("u1")


def test_cuts_at_max_words_without_a_boundary():
    p = Phraser(min_words=3, max_words=5)
    words = "one two three four five six seven"
    text, _, _ = p.partial("u1", words, words, 500)
    assert text == "one two three four five"


def test_volatile_words_are_never_cut():
    p = Phraser(min_words=2, max_words=4)
    assert p.partial("u1", "alpha", "alpha beta gamma delta epsilon", 100) is None


def test_final_returns_only_the_tail():
    p = Phraser(min_words=3, max_words=3)
    p.partial("u1", "a b c d", "a b c d", 100)
    assert p.final("u1", "a b c, d e.") == "d e."
    assert not p.covered("u1")
    assert p.final("u2", "fresh line.") == "fresh line."


def test_final_with_nothing_left_is_empty():
    p = Phraser(min_words=2, max_words=2)
    p.partial("u1", "a b", "a b", 100)
    assert p.final("u1", "a b.") == ""


def test_parses_partial_and_speech_end_events():
    ev = parse_ws_message('{"type":"partial_transcript","text":"a b c","stable_text":"a b","volatile_text":"c"}')
    assert ev and ev.kind == "partial" and ev.stable_text == "a b" and ev.text == "a b c"
    end = parse_ws_message('{"type":"speech_end","t_ms":14560,"audio_ms":14496}')
    assert end and end.kind == "processing" and end.t_ms == 14560
    fin = parse_ws_message('{"type":"final_transcript","text":"a b c.","is_final":true}')
    assert fin and fin.kind == "final" and fin.text == "a b c."


def test_next_utterance_starting_early_does_not_lose_the_previous_one():
    """Prisma sends the next utterance's first partial before the previous final: the tail must still be the tail."""
    p = Phraser(min_words=3, max_words=3)
    assert p.partial("u1", "a b c d", "a b c d", 100)[0] == "a b c"
    assert p.partial("u2", "x", "x y", 200) is None
    assert p.covered("u1") and not p.covered("u2")
    assert p.final("u1", "a b c d e.") == "d e."


def test_tail_is_found_by_the_last_words_when_the_final_differs():
    p = Phraser(min_words=4, max_words=4)
    assert p.partial("u1", "we cook it here", "we cook it here for", 100)[0] == "we cook it here"
    # the final decode inserted a word early on: counting words alone would repeat "here"
    assert p.final("u1", "Well, we cook it here, for an hour.") == "for an hour."


def test_spots_a_line_the_model_did_not_translate():
    from app.providers.llm_openai import looks_untranslated
    src = "और taste इसका ऐसा test है"
    assert looks_untranslated(src, src, "en-IN")
    assert looks_untranslated(src, src, "ta-IN")
    assert not looks_untranslated("and it tastes so good", src, "en-IN")
    assert not looks_untranslated("இந்த grill chicken-அ நான் சாப்பிடுவேன்", src, "ta-IN")
    assert not looks_untranslated(src, src, "mr-IN")  # same script: cannot tell, so never flagged
    # a stray word in a third script inside an otherwise Tamil line
    assert looks_untranslated("நான் சொல்றேன் \u10db\u10d7\u10d4\u10da\u10d8 Delhi-ல இந்த taste.", src, "ta-IN")
    assert looks_untranslated("அதே oil-லதான் \u09ac\u09be\u09b0\u09ac\u09be\u09b0", src, "ta-IN")
    assert not looks_untranslated("ਮੈਂ ਇਹ grill chicken ਖੁਦ ਖਾਂਦਾ ਹਾਂ।", src, "pa-IN")
    assert not looks_untranslated("আমি নিজে এই grill chicken খাই — সত্যি!", src, "bn-IN")
    assert looks_untranslated("", src, "en-IN")


def test_trim_pcm_silence_and_tempo():
    import numpy as np

    from app.shared import audio_utils as au

    sr = 24000
    tone = (np.sin(np.arange(sr) * 2 * np.pi * 220 / sr) * 8000).astype("<i2")
    quiet = np.zeros(sr // 2, dtype="<i2")
    pcm = np.concatenate([quiet, tone, quiet]).tobytes()
    both = au.trim_pcm_silence(pcm, start=True, end=True, sr=sr)
    assert abs(len(both) / 2 / sr - 1.08) < 0.02          # 1 s of tone plus 40 ms kept on each side
    head = au.trim_pcm_silence(pcm, start=True, end=False, sr=sr)
    assert abs(len(head) / 2 / sr - 1.54) < 0.02
    assert au.trim_pcm_silence(quiet.tobytes(), start=True, end=False) == b""
    assert au.trim_pcm_silence(quiet.tobytes(), start=False, end=True) == quiet.tobytes()
    try:
        au.ffmpeg_bin()
    except au.FFmpegError:
        return
    fast = au.tempo_pcm(tone.tobytes(), sr, 1.25)
    assert abs(len(fast) / 2 / sr - 0.8) < 0.05
