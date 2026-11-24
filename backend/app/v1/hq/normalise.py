"""Studio HQ: the per-language normaliser (`V1_HQ_NORMALISE`). Rules, no model.

Before a line reaches the voice engine, what a voice cannot read as written is written out in the target
language's own words and letters: numbers, decimals, dates, clock times, the rupee sign, the dollar sign, %,
a few units and short forms, and (for our own voice engine, which reads only the language's own letters)
abbreviations in capital letters, letter by letter.

Covered: Hindi (hi-IN), Bengali (bn-IN), Tamil (ta-IN), English (en-IN). For every other language `covered()`
is False and the line is left as it is (the HQ path's model-written step still handles it).

The rules know nothing about grammar: "₹500" becomes "five hundred rupees" in the language's words, in that
order, and a line that needs a case ending after it keeps the ending it had.
"""
import re

COVERED = ("hi-IN", "bn-IN", "ta-IN", "en-IN")

HI = ("शून्य एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस बीस "
      "इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस इकतीस बत्तीस तैंतीस चौंतीस पैंतीस छत्तीस सैंतीस "
      "अड़तीस उनतालीस चालीस इकतालीस बयालीस तैंतालीस चौवालीस पैंतालीस छियालीस सैंतालीस अड़तालीस उनचास पचास इक्यावन "
      "बावन तिरपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ साठ इकसठ बासठ तिरसठ चौंसठ पैंसठ छियासठ सड़सठ अड़सठ उनहत्तर "
      "सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर पचहत्तर छिहत्तर सतहत्तर अठहत्तर उनासी अस्सी इक्यासी बयासी तिरासी चौरासी "
      "पचासी छियासी सत्तासी अट्ठासी नवासी नब्बे इक्यानवे बानवे तिरानवे चौरानवे पंचानवे छियानवे सत्तानवे अट्ठानवे "
      "निन्यानवे").split()
BN = ("শূন্য এক দুই তিন চার পাঁচ ছয় সাত আট নয় দশ এগারো বারো তেরো চৌদ্দ পনেরো ষোলো সতেরো আঠারো উনিশ বিশ "
      "একুশ বাইশ তেইশ চব্বিশ পঁচিশ ছাব্বিশ সাতাশ আটাশ ঊনত্রিশ ত্রিশ একত্রিশ বত্রিশ তেত্রিশ চৌত্রিশ পঁয়ত্রিশ ছত্রিশ "
      "সাঁইত্রিশ আটত্রিশ ঊনচল্লিশ চল্লিশ একচল্লিশ বিয়াল্লিশ তেতাল্লিশ চুয়াল্লিশ পঁয়তাল্লিশ ছেচল্লিশ সাতচল্লিশ "
      "আটচল্লিশ ঊনপঞ্চাশ পঞ্চাশ একান্ন বায়ান্ন তিপ্পান্ন চুয়ান্ন পঞ্চান্ন ছাপ্পান্ন সাতান্ন আটান্ন ঊনষাট ষাট একষট্টি "
      "বাষট্টি তেষট্টি চৌষট্টি পঁয়ষট্টি ছেষট্টি সাতষট্টি আটষট্টি ঊনসত্তর সত্তর একাত্তর বাহাত্তর তিয়াত্তর চুয়াত্তর "
      "পঁচাত্তর ছিয়াত্তর সাতাত্তর আটাত্তর ঊনআশি আশি একাশি বিরাশি তিরাশি চুরাশি পঁচাশি ছিয়াশি সাতাশি আটাশি "
      "ঊননব্বই নব্বই একানব্বই বিরানব্বই তিরানব্বই চুরানব্বই পঁচানব্বই ছিয়ানব্বই সাতানব্বই আটানব্বই নিরানব্বই").split()
TA_UNITS = ("பூஜ்ஜியம் ஒன்று இரண்டு மூன்று நான்கு ஐந்து ஆறு ஏழு எட்டு ஒன்பது பத்து பதினொன்று பன்னிரண்டு பதிமூன்று "
            "பதினான்கு பதினைந்து பதினாறு பதினேழு பதினெட்டு பத்தொன்பது").split()
TA_TENS = "- - இருபது முப்பது நாற்பது ஐம்பது அறுபது எழுபது எண்பது தொண்ணூறு".split()
TA_TENS_JOIN = "- - இருபத்து முப்பத்து நாற்பத்து ஐம்பத்து அறுபத்து எழுபத்து எண்பத்து தொண்ணூற்று".split()
TA_HUNDREDS = "- நூறு இருநூறு முந்நூறு நானூறு ஐநூறு அறுநூறு எழுநூறு எண்ணூறு தொள்ளாயிரம்".split()
TA_HUNDREDS_JOIN = "- நூற்று இருநூற்று முந்நூற்று நானூற்று ஐநூற்று அறுநூற்று எழுநூற்று எண்ணூற்று தொள்ளாயிரத்து".split()
TA_THOUSANDS = "- ஆயிரம் இரண்டாயிரம் மூவாயிரம் நான்காயிரம் ஐயாயிரம் ஆறாயிரம் ஏழாயிரம் எட்டாயிரம் ஒன்பதாயிரம் பத்தாயிரம்".split()
EN_UNITS = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
            "seventeen eighteen nineteen").split()
EN_TENS = "- - twenty thirty forty fifty sixty seventy eighty ninety".split()
assert len(HI) == 100 and len(BN) == 100 and len(TA_UNITS) == 20

# Words that differ by language. `mult` are the big-number words a figure can be followed by ("2.5 lakh").
WORDS: dict[str, dict[str, str]] = {
    "hi-IN": {"hundred": "सौ", "thousand": "हज़ार", "lakh": "लाख", "crore": "करोड़", "point": "दशमलव", "percent": "प्रतिशत",
              "rupees": "रुपये", "dollars": "डॉलर", "to": "से", "and": "और", "plus": "प्लस", "equals": "बराबर", "at": "ऐट",
              "minus": "माइनस"},
    "bn-IN": {"hundred": "শো", "thousand": "হাজার", "lakh": "লক্ষ", "crore": "কোটি", "point": "দশমিক", "percent": "শতাংশ",
              "rupees": "টাকা", "dollars": "ডলার", "to": "থেকে", "and": "এবং", "plus": "প্লাস", "equals": "সমান", "at": "অ্যাট",
              "minus": "মাইনাস"},
    "ta-IN": {"hundred": "நூறு", "thousand": "ஆயிரம்", "lakh": "லட்சம்", "crore": "கோடி", "point": "புள்ளி", "percent": "சதவீதம்",
              "rupees": "ரூபாய்", "dollars": "டாலர்", "to": "முதல்", "and": "மற்றும்", "plus": "பிளஸ்", "equals": "சமம்", "at": "அட்",
              "minus": "மைனஸ்"},
    "en-IN": {"hundred": "hundred", "thousand": "thousand", "lakh": "lakh", "crore": "crore", "point": "point",
              "percent": "percent", "rupees": "rupees", "dollars": "dollars", "to": "to", "and": "and", "plus": "plus",
              "equals": "equals", "at": "at", "minus": "minus"},
}
MONTHS = {
    "hi-IN": "जनवरी फ़रवरी मार्च अप्रैल मई जून जुलाई अगस्त सितंबर अक्टूबर नवंबर दिसंबर".split(),
    "bn-IN": "জানুয়ারি ফেব্রুয়ারি মার্চ এপ্রিল মে জুন জুলাই আগস্ট সেপ্টেম্বর অক্টোবর নভেম্বর ডিসেম্বর".split(),
    "ta-IN": "ஜனவரி பிப்ரவரி மார்ச் ஏப்ரல் மே ஜூன் ஜூலை ஆகஸ்ட் செப்டம்பர் அக்டோபர் நவம்பர் டிசம்பர்".split(),
    "en-IN": "January February March April May June July August September October November December".split(),
}
UNITS = {   # written after a figure
    "km": {"hi-IN": "किलोमीटर", "bn-IN": "কিলোমিটার", "ta-IN": "கிலோமீட்டர்", "en-IN": "kilometres"},
    "kg": {"hi-IN": "किलो", "bn-IN": "কেজি", "ta-IN": "கிலோ", "en-IN": "kilos"},
    "cm": {"hi-IN": "सेंटीमीटर", "bn-IN": "সেন্টিমিটার", "ta-IN": "சென்டிமீட்டர்", "en-IN": "centimetres"},
    "mm": {"hi-IN": "मिलीमीटर", "bn-IN": "মিলিমিটার", "ta-IN": "மில்லிமீட்டர்", "en-IN": "millimetres"},
    "ml": {"hi-IN": "मिलीलीटर", "bn-IN": "মিলিলিটার", "ta-IN": "மில்லிலிட்டர்", "en-IN": "millilitres"},
    "gb": {"hi-IN": "जीबी", "bn-IN": "জিবি", "ta-IN": "ஜிபி", "en-IN": "GB"},
    "mb": {"hi-IN": "एमबी", "bn-IN": "এমবি", "ta-IN": "எம்பி", "en-IN": "MB"},
}
SHORT = {   # short forms with a full stop or of two letters, whole words only
    "dr.": {"hi-IN": "डॉक्टर", "bn-IN": "ডাক্তার", "ta-IN": "டாக்டர்", "en-IN": "Doctor"},
    "mr.": {"hi-IN": "मिस्टर", "bn-IN": "মিস্টার", "ta-IN": "மிஸ்டர்", "en-IN": "Mister"},
    "mrs.": {"hi-IN": "मिसेज़", "bn-IN": "মিসেস", "ta-IN": "மிஸஸ்", "en-IN": "Missus"},
    "vs.": {"hi-IN": "बनाम", "bn-IN": "বনাম", "ta-IN": "எதிராக", "en-IN": "versus"},
    "vs": {"hi-IN": "बनाम", "bn-IN": "বনাম", "ta-IN": "எதிராக", "en-IN": "versus"},
    "etc.": {"hi-IN": "आदि", "bn-IN": "ইত্যাদি", "ta-IN": "முதலியன", "en-IN": "et cetera"},
}
LETTERS = {   # the names of the Latin letters A-Z as each script writes them
    "hi-IN": "ए बी सी डी ई एफ जी एच आई जे के एल एम एन ओ पी क्यू आर एस टी यू वी डब्ल्यू एक्स वाई ज़ेड".split(),
    "bn-IN": "এ বি সি ডি ই এফ জি এইচ আই জে কে এল এম এন ও পি কিউ আর এস টি ইউ ভি ডব্লিউ এক্স ওয়াই জেড".split(),
    "ta-IN": "ஏ பி சி டி ஈ எஃப் ஜி எச் ஐ ஜே கே எல் எம் என் ஓ பி க்யூ ஆர் எஸ் டி யூ வி டபிள்யூ எக்ஸ் ஒய் இசட்".split(),
}
MULT = {"lakh": "lakh", "lakhs": "lakh", "lac": "lakh", "lacs": "lakh", "लाख": "lakh", "লাখ": "lakh", "লক্ষ": "lakh",
        "லட்சம்": "lakh", "crore": "crore", "crores": "crore", "cr": "crore", "करोड़": "crore", "কোটি": "crore",
        "கோடி": "crore", "thousand": "thousand", "हज़ार": "thousand", "हजार": "thousand", "হাজার": "thousand",
        "ஆயிரம்": "thousand"}
NATIVE_DIGITS = str.maketrans("०१२३४५६७८९০১২৩৪৫৬৭৮৯௦௧௨௩௪௫௬௭௮௯", "0123456789" * 3)

NUM = r"\d+(?:,\d+)*(?:\.\d+)?"
MULT_RE = "|".join(sorted(map(re.escape, MULT), key=len, reverse=True))
DATE = re.compile(r"(?<![\d/.-])(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})(?![\d/-])")
CLOCK = re.compile(r"(?<![\d:.])(\d{1,2}):(\d{2})(?![\d:])")
RUPEES = re.compile(rf"(?:₹|\bRs\.?|\bINR)\s*({NUM})(?:\s*({MULT_RE})(?![^\W\d_]))?", re.IGNORECASE)
DOLLARS = re.compile(rf"\$\s*({NUM})")
PERCENT = re.compile(rf"({NUM})\s*%")
UNIT = re.compile(rf"({NUM})\s*({'|'.join(UNITS)})\b", re.IGNORECASE)
RANGE = re.compile(rf"(?<![\d,.])({NUM})\s*[-–]\s*({NUM})(?![\d,])")
NUMBER = re.compile(NUM)
CAPS = re.compile(r"(?<![A-Za-z])[A-Z]{2,5}(?![A-Za-z])")
SHORT_RE = re.compile(r"(?<![^\W\d_])(" + "|".join(sorted(map(re.escape, SHORT), key=len, reverse=True)) + r")(?![^\W\d_])",
                      re.IGNORECASE)
SYMBOLS = {"&": "and", "+": "plus", "=": "equals", "@": "at"}


def covered(lang: str) -> bool:
    return lang in COVERED


# ---------- whole numbers ----------
def _hi(n: int) -> str:
    if n < 100:
        return HI[n]
    w = WORDS["hi-IN"]
    for size, name in ((10_000_000, "crore"), (100_000, "lakh"), (1000, "thousand"), (100, "hundred")):
        if n >= size:
            head, rest = divmod(n, size)
            return f"{_hi(head)} {w[name]}" + (f" {_hi(rest)}" if rest else "")
    raise AssertionError


def _bn(n: int) -> str:
    if n < 100:
        return BN[n]
    w = WORDS["bn-IN"]
    if n < 1000:
        head, rest = divmod(n, 100)
        return BN[head] + w["hundred"] + (f" {_bn(rest)}" if rest else "")
    for size, name in ((10_000_000, "crore"), (100_000, "lakh"), (1000, "thousand")):
        if n >= size:
            head, rest = divmod(n, size)
            return f"{_bn(head)} {w[name]}" + (f" {_bn(rest)}" if rest else "")
    raise AssertionError


def _ta(n: int) -> str:
    if n < 20:
        return TA_UNITS[n]
    if n < 100:
        tens, unit = divmod(n, 10)
        return TA_TENS[tens] if not unit else f"{TA_TENS_JOIN[tens]} {TA_UNITS[unit]}"
    if n < 1000:
        head, rest = divmod(n, 100)
        return TA_HUNDREDS[head] if not rest else f"{TA_HUNDREDS_JOIN[head]} {_ta(rest)}"
    if n < 100_000:
        head, rest = divmod(n, 1000)
        word = TA_THOUSANDS[head] if head <= 10 else f"{_ta(head)} ஆயிரம்"
        return word if not rest else f"{word[:-2]}த்து {_ta(rest)}"      # ஆயிரம் -> ஆயிரத்து before more
    if n < 10_000_000:
        head, rest = divmod(n, 100_000)
        word = ("ஒரு" if head == 1 else _ta(head)) + " "
        return word + ("லட்சம்" if not rest else f"லட்சத்து {_ta(rest)}")
    head, rest = divmod(n, 10_000_000)
    word = ("ஒரு" if head == 1 else _ta(head)) + " "
    return word + ("கோடி" if not rest else f"கோடியே {_ta(rest)}")


def _en(n: int) -> str:
    if n < 20:
        return EN_UNITS[n]
    if n < 100:
        tens, unit = divmod(n, 10)
        return EN_TENS[tens] + (f"-{EN_UNITS[unit]}" if unit else "")
    for size, name in ((10_000_000, "crore"), (100_000, "lakh"), (1000, "thousand"), (100, "hundred")):
        if n >= size:
            head, rest = divmod(n, size)
            return f"{_en(head)} {name}" + (f" {_en(rest)}" if rest else "")
    raise AssertionError


_WHOLE = {"hi-IN": _hi, "bn-IN": _bn, "ta-IN": _ta, "en-IN": _en}


def number_words(n: int, lang: str) -> str:
    """A whole number from 0 to 99,99,99,999 in the language's words, counted the Indian way (lakh, crore)."""
    if lang not in _WHOLE or not 0 <= n < 1_000_000_000:
        raise ValueError(f"no number words for {n} in {lang}")
    return _WHOLE[lang](n)


def _figure(text: str, lang: str, *, plain: bool = False) -> str:
    """A written figure ("1,50,000", "2.5", "1947") as words. `plain` = a bare number, where 1100-1999 is read by
    its hundreds ("nineteen hundred forty-seven": how a year and a round amount are both said) outside Tamil."""
    whole, _, frac = text.replace(",", "").partition(".")
    n = int(whole)
    if n >= 1_000_000_000:     # too long to be a quantity (a phone number): digit by digit
        return " ".join(number_words(int(d), lang) for d in whole + frac)
    if plain and not frac and 1100 <= n <= 1999 and n % 100 and lang != "ta-IN":
        w = WORDS[lang]["hundred"]
        head = number_words(n // 100, lang)
        out = (head + w if lang == "bn-IN" else f"{head} {w}") + " " + number_words(n % 100, lang)
    else:
        out = number_words(n, lang)
    if frac:
        out += f" {WORDS[lang]['point']} " + " ".join(number_words(int(d), lang) for d in frac)
    return out


# ---------- a line ----------
def spoken(text: str, lang: str, native: bool = False) -> str:
    """The line with figures, signs and short forms written as words of `lang`. `native` = the line is for our
    own voice engine, which reads only the language's own letters: abbreviations in capitals are spelled out too.
    A language that is not covered, and a line with nothing to write out, comes back unchanged."""
    if not covered(lang) or not text:
        return text
    w = WORDS[lang]
    out = text.translate(NATIVE_DIGITS)

    def pad(s: str) -> str:
        return f" {s} "

    def date(m: re.Match[str]) -> str:
        day, month = int(m.group(1)), int(m.group(2))
        if not (1 <= day <= 31 and 1 <= month <= 12):
            return m.group(0)
        return pad(f"{number_words(day, lang)} {MONTHS[lang][month - 1]} {_figure(m.group(3), lang, plain=True)}")

    def clock(m: re.Match[str]) -> str:
        h, mins = int(m.group(1)), int(m.group(2))
        if h > 23 or mins > 59:
            return m.group(0)
        hw, mw = number_words(h, lang), number_words(mins, lang)
        if lang == "hi-IN":
            return pad(f"{hw} बजे" if not mins else f"{hw} बजकर {mw} मिनट")
        if lang == "bn-IN":
            return pad(f"{hw}টা" if not mins else f"{hw}টা {mw}")
        if lang == "ta-IN":
            return pad(f"{hw} மணி" if not mins else f"{hw} மணி {mw} நிமிடம்")
        return pad(f"{hw} o'clock" if not mins else f"{hw} {'oh ' if mins < 10 else ''}{mw}")

    def money(m: re.Match[str]) -> str:
        mult = MULT.get((m.group(2) or "").lower())
        return pad(_figure(m.group(1), lang) + (f" {w[mult]}" if mult else "") + f" {w['rupees']}")

    out = DATE.sub(date, out)
    out = CLOCK.sub(clock, out)
    out = RUPEES.sub(money, out)
    out = DOLLARS.sub(lambda m: pad(f"{_figure(m.group(1), lang)} {w['dollars']}"), out)
    out = PERCENT.sub(lambda m: pad(f"{_figure(m.group(1), lang)} {w['percent']}"), out)
    out = UNIT.sub(lambda m: pad(f"{_figure(m.group(1), lang)} {UNITS[m.group(2).lower()][lang]}"), out)
    out = RANGE.sub(lambda m: pad(f"{_figure(m.group(1), lang, plain=True)} {w['to']} {_figure(m.group(2), lang, plain=True)}"), out)
    out = NUMBER.sub(lambda m: pad(_figure(m.group(0), lang, plain=True)), out)
    out = SHORT_RE.sub(lambda m: SHORT[m.group(1).lower()][lang], out)
    for sign, name in SYMBOLS.items():
        out = out.replace(sign, pad(w[name]))
    out = out.replace("₹", pad(w["rupees"])).replace("%", pad(w["percent"])).replace("$", pad(w["dollars"]))
    if native and lang in LETTERS:
        out = CAPS.sub(lambda m: pad(" ".join(LETTERS[lang][ord(c) - 65] for c in m.group(0))), out)
    out = re.sub(r"\s+", " ", out).strip()
    return re.sub(r"\s+([,.!?;:।])", r"\1", out)


def spoken_lines(lines: list[str], lang: str, native: bool = False) -> tuple[list[str], int]:
    """Every line normalised. Returns the lines and how many changed."""
    out = [spoken(t, lang, native) for t in lines]
    return out, sum(1 for a, b in zip(lines, out) if a != b)
