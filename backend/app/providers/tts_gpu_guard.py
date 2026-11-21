"""GPU engine only: catches lines the IndicF5 engine swallows, and keeps every line in the one copied voice.

Measured 2026-11-21 on 120 real live phrases, each spoken twice: the bad lines are short ones. The engine gives a
line time by its length against the sample's, and a line of 2-4 words often gets so little that nothing is spoken
(Bengali: 12 of 13 lines that came out under 0.6x their usual length were lost). Making the same line again rarely
helps (1 of 11). Lines of 2-4 words, words heard back by Prisma, IndicF5 / IndicF5 at speed 0.75 / Indic-Mio:
Tamil 71 / 78 / 85%, Bengali 33 / 67 / 81%. Lines of 6 and more words are fine on IndicF5 (83-84%).

A first version gave short lines to Indic-Mio. On a real stream a third of the lines were short, and the viewer
heard a second voice between the copied one (closeness to the sample 0.39 against 0.67). So by default
(`gpu_voice_short_engine` = f5) a short line stays on IndicF5 and is given more time (speed x
`gpu_voice_short_speed`), and a line that still comes out far too short is made again slower. `mio` restores the
second voice for short and swallowed lines.
"""
import statistics
from typing import Any

from app.shared import audio_utils as au

MIN_SPEECH_MS = 150       # less speech than this is no line at all
SHORT_AGAINST_USUAL = 0.5
MIN_LINES = 5             # lines heard from a voice before "usual" means anything


class GuardedVoice:
    def __init__(self, main: Any, second: Any, settings: Any) -> None:
        self.main, self.second, self.s = main, second, settings
        self._second_has: set[str] = set()
        self._usual: dict[tuple[str, str], list[float]] = {}   # (session, lang) -> speech ms a letter at speed 1
        self.short_lines = 0    # lines given to the second voice for being short
        self.rescued = 0        # lines made again because the first try was swallowed

    def __getattr__(self, name: str) -> Any:   # everything else is the main engine's
        return getattr(self.main, name)

    async def set_ref(self, session_id: str, wav_path: str, ref_text: str, **kw: Any) -> dict[str, Any]:
        out = await self.main.set_ref(session_id, wav_path, ref_text, **kw)
        if self.s.gpu_voice_short_engine == "mio" and self.second is not None and self.second.enabled:
            try:
                await self.second.set_ref(session_id, wav_path, "", consent_at=kw.get("consent_at"))
                self._second_has.add(session_id)
            except Exception:  # noqa: BLE001 - the second voice is a help, never a reason to fail
                self._second_has.discard(session_id)
        return dict(out)

    def _second_for(self, session_id: str, lang: str) -> bool:
        return self.second is not None and session_id in self._second_has and self.second.speaks(lang)

    @staticmethod
    def _speech_ms(pcm: bytes, rate: int) -> float:
        cut = au.trim_pcm_silence(au.trim_pcm_silence(pcm, start=True, end=False, sr=rate), start=False, end=True, sr=rate)
        return len(cut) / 2 / rate * 1000

    async def synth(self, session_id: str, text: str, lang: str, speed: float | None = None) -> tuple[bytes, int]:
        words, letters = len(text.split()), max(1, len(text.replace(" ", "")))
        use_second = self.s.gpu_voice_short_engine == "mio" and self._second_for(session_id, lang)
        short = 0 < words <= self.s.gpu_voice_short_words
        if short and use_second:
            try:
                out = await self.second.synth(session_id, text, lang)
                self.short_lines += 1
                return out
            except Exception:  # noqa: BLE001
                pass
        ask = (speed or 1.0) * (self.s.gpu_voice_short_speed if short else 1.0)
        if short:
            self.short_lines += 1
        pcm, rate = await self.main.synth(session_id, text, lang, speed=ask)
        speech = self._speech_ms(pcm, rate)
        per_letter = speech * ask / letters
        usual = self._usual.setdefault((session_id, lang), [])
        floor = SHORT_AGAINST_USUAL * statistics.median(usual) if len(usual) >= MIN_LINES else 0.0
        if speech >= MIN_SPEECH_MS and per_letter >= floor:
            if not short:
                usual.append(per_letter)
                del usual[:-40]
            return pcm, rate
        try:
            if use_second:
                out = await self.second.synth(session_id, text, lang)
            else:
                out = await self.main.synth(session_id, text, lang, speed=ask * 0.75)
            self.rescued += 1
            return out
        except Exception:  # noqa: BLE001
            return pcm, rate
