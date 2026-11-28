"""A long line is cut into several at its sentences, so the dub follows the video to its end."""
import numpy as np

from app.studio.stages import fit, split

SENTENCES = ["आज हम एक नई चीज़ बनाएंगे जो आपने पहले नहीं देखी होगी।", "सबसे पहले हम मसाला तैयार करते हैं और उसे अच्छे से भूनते हैं।",
             "इसके बाद चिकन को डेढ़ घंटे मशीन में पकाते हैं।", "फिर इसे गरम गरम परोसते हैं और ऊपर से नींबू डालते हैं।",
             "इसमें कोई रंग नहीं होगा और कोई खराब चीज़ नहीं होगी।"]
TEXT = " ".join(SENTENCES)


def test_a_short_line_and_a_switched_off_split_stay_one_line():
    assert split.split_line(1.0, 7.0, TEXT, 10.0) == [(1.0, 7.0, TEXT)]
    assert split.split_line(0.1, 24.9, TEXT, 0) == [(0.1, 24.9, TEXT)]
    assert split.split_line(0.0, 20.0, "हाँ ठीक है", 10.0) == [(0.0, 20.0, "हाँ ठीक है")]


def test_a_long_line_becomes_lines_of_a_few_seconds_that_cover_it_without_a_gap():
    out = split.split_line(0.1, 24.9, TEXT, 10.0)
    assert len(out) >= 3
    assert out[0][0] == 0.1 and out[-1][1] == 24.9
    assert all(a[1] == b[0] for a, b in zip(out, out[1:]))                 # each starts where the last ended
    assert all(e - s >= split.MIN_PIECE_S / 2 and e - s <= 10.0 for s, e, _ in out)
    assert " ".join(t for _, _, t in out).split() == TEXT.split()         # no word lost, none added, same order
    # The last line starts late in the video: its dub is spoken there, not at the start.
    assert out[-1][0] > 15.0
    slots = fit.slots([s for s, _, _ in out], 25.0)
    assert max(slots) <= 10.0


def test_pieces_are_sentences_and_a_sentence_without_marks_is_cut_by_words():
    assert split.pieces(TEXT, 20) == SENTENCES
    words = " ".join(f"w{i}" for i in range(60))
    out = split.split_line(0.0, 24.0, words, 10.0)
    assert len(out) >= 3 and " ".join(t for _, _, t in out) == words
    assert max(len(t.split()) for _, _, t in out) <= 20


def test_a_cut_moves_to_the_quiet_moment_nearby():
    audio = np.ones(25 * split.SR, dtype=np.float32) * 0.3
    audio[int(12.2 * split.SR):int(12.4 * split.SR)] = 0.0                 # a pause at 12.2-12.4 s
    assert 12.2 <= split.quiet_near(audio, 12.0, 0.0, 25.0) <= 12.4
    assert split.quiet_near(None, 12.0, 0.0, 25.0) == 12.0


def test_every_segment_goes_through_and_a_piece_keeps_its_language():
    segs = [(0.0, 3.0), (3.5, 28.0)]
    results = [{"text": "नमस्ते दोस्तों", "lang": "hi-IN"}, {"text": TEXT, "lang": "hi-IN"}]
    new_segs, new_results = split.split_long(segs, results, 10.0)
    assert new_segs[0] == (0.0, 3.0) and new_results[0]["text"] == "नमस्ते दोस्तों"
    assert len(new_segs) == len(new_results) > 3 and new_segs[-1][1] == 28.0
    assert all(r["lang"] == "hi-IN" for r in new_results)
