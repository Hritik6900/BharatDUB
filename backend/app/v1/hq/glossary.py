"""Studio HQ: glossary candidates from the job's own transcript (`V1_HQ_AUTO_GLOSSARY`). Rules, no model.

What is proposed, from the lines of one video:

  name    a word (or a run of words) in Latin letters that starts with a capital and is not the first word of
          its line, or a word with a capital inside it (YouTube, iPhone): a person, a place, a brand
  short   an abbreviation in capitals (DNA, GST, IPL), with or without digits (T20, 5G)
  term    any other word in Latin letters that is said in two or more lines of a transcript that is otherwise
          not in Latin letters (an English term inside Hindi speech: "enzyme", "playlist")
  repeat  a word in the transcript's own script that is said in at least three lines, is long, and is not one
          of the very common words: likely a subject word. Offered last, and only as a candidate.

A transcript written wholly in Latin letters (our GPU speech-to-text writes Hinglish that way) has no "term"
candidates, because every word would be one; names and abbreviations are still found.

The candidates are for this job only: they are added to the glossary its text steps get, stored with the job, and
never written to the shared glossary. A person can take one over on the glossary page.
"""
import re
import unicodedata
from typing import Any

LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z0-9'’-]*")


def _spans(text: str) -> list[tuple[int, str]]:
    """(start, word) for every word of any script. Vowel signs and other marks belong to their word (the regex's
    word class does not know them and would cut an Indian word at every sign)."""
    out: list[tuple[int, str]] = []
    start = -1
    for i, c in enumerate(text + " "):
        if unicodedata.category(c)[0] in "LMN":
            start = i if start < 0 else start
        elif start >= 0:
            out.append((start, text[start:i]))
            start = -1
    return out

# Latin-letter words that are not worth a glossary line: English function words and the commonest Hinglish ones.
COMMON = frozenset("""a an the and or but so if of to in on at by for from with as is are was were be been it its this
that these those i you he she we they me my your his her our their not no yes ok okay hi hello hey thanks thank please
very more most much many some any all one two three first next now then here there what when where who why how can
will would should could do does did done have has had get got go going come make made like just also only really
aaj kal hum main tum aap yeh woh ye wo hai hain tha thi the ho hoga hogi kya kyun kaise kab kahan nahi nahin haan ji
ka ki ke ko se me mein par aur ya lekin toh to bhi hi na kar karo karna raha rahi rahe gaya gayi gaye liye wala wali
ek do teen sab kuch bahut accha theek chalo dekho bolo suno matlab abhi phir fir jab tab agar""".split())


def _is_latin(word: str) -> bool:
    return all("LATIN" in unicodedata.name(c, "") or not c.isalpha() for c in word)


def _latin_share(lines: list[str]) -> float:
    letters = [c for t in lines for c in t if c.isalpha()]
    return sum(1 for c in letters if "LATIN" in unicodedata.name(c, "")) / len(letters) if letters else 0.0


def _kind(word: str, *, starts_line: bool, latin_text: bool) -> str:
    """name | short | term | "" for one word in Latin letters."""
    if len(word) < 2 or word.lower() in COMMON:
        return ""
    if re.fullmatch(r"[A-Z]{2,6}|[A-Z]+\d+[A-Z]*|\d+[A-Z]{1,2}", word):
        return "short"
    if any(c.isupper() for c in word[1:]):
        return "name"             # a capital inside: YouTube, iPhone
    if word[0].isupper():
        # In a transcript in Latin letters every line starts with a capital; in any other a capital is a choice.
        return "" if latin_text and starts_line else "name"
    return "" if latin_text or len(word) < 3 else "term"


def candidates(lines: list[str], known: list[str] | None = None, limit: int = 40) -> list[dict[str, Any]]:
    """[{term, kind, lines}] best first: names and abbreviations, then English terms, then repeated words.
    `known` (the shared glossary) is left out; one spelling per word (the first one seen)."""
    have = {k.lower() for k in known or []}
    mostly_latin = _latin_share(lines) > 0.6
    found: dict[str, dict[str, Any]] = {}

    def add(term: str, kind: str, i: int) -> None:
        key = term.lower()
        if key in have or key in COMMON or len(term) < 2:
            return
        row = found.setdefault(key, {"term": term, "kind": kind, "in": set()})
        row["in"].add(i)
        if kind in ("name", "short") and row["kind"] not in ("name", "short"):
            row["kind"] = kind

    for i, line in enumerate(lines):
        spans = _spans(line)
        first_start = spans[0][0] if spans else -1
        run: list[str] = []
        last_end = -2

        def flush() -> None:
            if len(run) > 1:
                add(" ".join(run), "name", i)
            run.clear()
        for m in LATIN_WORD.finditer(line):
            word = m.group(0).strip("'’-")
            kind = _kind(word, starts_line=m.start() == first_start, latin_text=mostly_latin)
            if kind != "name" or m.start() != last_end + 1:
                flush()            # a run of names is capitalised words with one space between them
            if kind:
                add(word, kind, i)
            if kind == "name":
                run.append(word)
                last_end = m.end()
        flush()
        if not mostly_latin:
            for _, word in spans:
                if not _is_latin(word) and not word[0].isdigit() and len(word) >= 5:
                    add(word, "repeat", i)

    out = []
    for row in found.values():
        n = len(row["in"])
        if row["kind"] == "term" and n < 2 or row["kind"] == "repeat" and n < 3:
            continue
        out.append({"term": row["term"], "kind": row["kind"], "lines": n})
    # a run of names ("Edward Jenner") replaces its single words when they are never said apart
    runs = [r for r in out if " " in r["term"]]
    for r in runs:
        for part in r["term"].split():
            single = next((x for x in out if x["term"].lower() == part.lower()), None)
            if single is not None and single["lines"] <= r["lines"]:
                out.remove(single)
    rank = {"name": 0, "short": 0, "term": 1, "repeat": 2}
    out.sort(key=lambda r: (rank[r["kind"]], -r["lines"], r["term"].lower()))
    return out[: max(0, limit)]


def terms(cands: list[dict[str, Any]], *, with_repeats: bool = False) -> list[str]:
    """The candidates as glossary words for the text steps. Repeated words in the transcript's own script are
    proposals for a person, not rules for the translator (they are ordinary words more often than names)."""
    return [c["term"] for c in cands if with_repeats or c["kind"] != "repeat"]
