"""The translation model on our own GPU (Gemma 4 E4B behind vLLM's OpenAI-compatible endpoint), for `AI_MODE=gpu`.

Same interface as `OpenAILLM`; only the live prompt differs. The hosted prompt grew rule by rule and ends by
overriding an earlier rule ("English words stay in Latin letters" ... "no Latin letters at all"). A small model
follows the first of two rules that disagree: measured 2026-11-21, 7-10 of 14 live lines came back with Latin words,
which the voice engine reads as noise. This prompt states each rule once, shows the model what an English word looks
like in the target script, and a line that still carries Latin letters is asked for once more.
"""
from app.config import LANG_NAMES
from app.providers.llm_openai import SCRIPTS, OpenAILLM, clean_line, wrong_script

# "game" and "chat" in each script: one look tells the model how English words are to be written.
SPELLED = {
    "hi-IN": "गेम, चैट", "mr-IN": "गेम, चॅट", "ta-IN": "கேம், சாட்", "bn-IN": "গেম, চ্যাট", "te-IN": "గేమ్, చాట్",
    "kn-IN": "ಗೇಮ್, ಚಾಟ್", "ml-IN": "ഗെയിം, ചാറ്റ്", "gu-IN": "ગેમ, ચેટ", "pa-IN": "ਗੇਮ, ਚੈਟ",
}


def has_latin(text: str) -> bool:
    return any("a" <= ch.lower() <= "z" for ch in text)


class LocalLLM(OpenAILLM):
    def _native(self, target: str) -> str:
        script = SCRIPTS.get(target)
        if not script:
            return ""
        return (f" Write every word in {script} letters, English words and names too, spelled the way they sound "
                f"(game, chat -> {SPELLED.get(target, '')}). No Latin letters.")

    async def translate_batch(self, lines: list[str], target: str, glossary: list[str]) -> list[str]:
        """Studio. Lines for our voice engine: it reads only the language's own letters, so the hosted prompt's
        "keep English words in English" does not apply. Checked line by line; a line with Latin letters is redone."""
        import json

        from app.providers.llm_openai import parse_json_array
        if not lines:
            return []
        lang = LANG_NAMES.get(target, target)
        system = (f"You dub short Indian videos. Translate each line from Hindi or Hinglish into natural spoken {lang}, "
                  "the way a creator talks on camera. Keep each line about as long to say as the source."
                  + self._native(target) +
                  " Return ONLY a JSON array of strings, same length and order as the input.")
        out: list[str] | None = None
        for _ in range(2):
            try:
                got = parse_json_array(await self._chat(system, json.dumps(lines, ensure_ascii=False), temperature=0.2,
                                                        max_tokens=3000))
            except ValueError:
                continue
            if len(got) == len(lines):
                out = got
                break
        if out is None:
            out = [""] * len(lines)
        script = SCRIPTS.get(target)
        for i, line in enumerate(lines):
            if not out[i].strip() or wrong_script(out[i], target) or (script and has_latin(out[i])):
                out[i] = await self.translate_chunk(line, target, glossary, lines[max(0, i - 2):i], native=True,
                                                    max_words=max(4, round(len(line.split()) * 1.3)))
        return out

    async def to_devanagari(self, text: str) -> str:
        """Hindi or Hinglish written in Latin letters (what the GPU speech-to-text writes) -> the same words in
        Devanagari. The voice engine lines its sample up with the sample's text, and it does that far better in
        Devanagari (measured 2026-11-21, same sample and lines: 91% / 87% of words heard back in Bengali / Tamil
        against 61% / 72% with the Latin text). Returns the text unchanged when the model's answer is not usable."""
        if not has_latin(text):
            return text
        system = ("This line is Hindi or Hinglish written in Latin letters. Write the same line in Devanagari: "
                  "Hindi words in their normal Devanagari spelling, English words in Devanagari the way they sound "
                  "(game -> गेम). Same words, same order, add nothing, remove nothing, do not translate. "
                  "Reply with the line only.")
        try:
            out = clean_line(await self._chat(system, text, temperature=0.0, max_tokens=400, timeout=8.0))
        except Exception:  # noqa: BLE001 - the Latin text still works, only less well
            return text
        n, m = len(text.split()), len(out.split())
        if not out or has_latin(out) or wrong_script(out, "hi-IN") or abs(n - m) > max(2, n // 4):
            return text
        return out

    async def shorten(self, text: str, target: str, max_seconds: float, max_words: int | None = None) -> str:
        lang = LANG_NAMES.get(target, target)
        limit = (f"It has {len(text.split())} words: rewrite it in at most {max_words} words. Keep the main points, "
                 "drop the rest." if max_words
                 else f"Rewrite this {lang} line so it can be spoken naturally in at most {max_seconds:.1f} seconds.")
        system = (f"This is a {lang} line of a dubbed video. " + limit + " Keep the meaning and the tone." + self._native(target) + " Reply with the rewritten line only.")
        return clean_line(await self._chat(system, text, temperature=0.2, max_tokens=300))

    async def translate_chunk(self, text: str, target: str, glossary: list[str], context: list[str],
                              brief: bool = False, native: bool = False, max_words: int | None = None) -> str:
        lang, script = LANG_NAMES.get(target, target), SCRIPTS.get(target)
        n = len(text.split())
        limit = max_words or (max(3, round(n * 0.6)) if brief else n)
        rules = [f"Translate the CURRENT line of a live stream from Hindi or Hinglish into spoken, everyday {lang}."]
        if script and native:
            rules.append(f"Write every word in {script} letters. English words, brand and game names too, spelled the way "
                         f"they sound (game, chat -> {SPELLED.get(target, '')}). No Latin letters, no Devanagari"
                         + ("" if script == "Devanagari" else " or any other script") + ", numbers as words.")
        elif script:
            keep = ", ".join(glossary) or "none"
            rules.append(f"Write in {script} letters, never romanised. Only these words stay in English letters: {keep}.")
        else:
            rules.append("Write natural spoken English in Latin letters. Leave no Hindi words.")
        rules.append(f"Use at most {limit} words. " + ("The dub is behind: say only the main point." if brief
                     else "Shorter is better: drop fillers such as bhai, yaar, matlab."))
        rules.append("CURRENT may be a piece of a sentence. Translate just that piece; do not finish the sentence, "
                     "do not repeat the previous lines, do not add anything.")
        rules.append("Reply with the translation only, on one line.")
        system = "\n".join(f"{i + 1}. {r}" for i, r in enumerate(rules))
        user = ("Previous lines (context only):\n" + "\n".join(context[-3:]) + "\n\n" if context else "") \
            + f"CURRENT: {text}"
        out = clean_line(await self._chat(system, user, temperature=0.2, max_tokens=200, timeout=8.0))
        if wrong_script(out, target) or (native and script and has_latin(out)):
            fix = (f"Rewrite this {lang} line with every word in {script} letters, spelled the way it sounds. "
                   "Change nothing else. Reply with the line only." if script
                   else "Rewrite this line in English only, in Latin letters. Reply with the line only.")
            again = clean_line(await self._chat(fix, out, temperature=0.0, max_tokens=200, timeout=8.0))
            if again and not wrong_script(again, target) and not (native and script and has_latin(again)):
                out = again
        return out
