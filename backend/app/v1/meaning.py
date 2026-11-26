"""v1.2 auto mode: the meaning check of a Live session. It never holds a phrase up.

A sample of the lines a language has spoken (every `v1_meaning_sample_every`-th while its budget is on, every
`v1_meaning_idle_every`-th while it is off) is put in a small queue; one worker judges them, one call at a time,
after the fact (`guards.judge`: the dub line beside its own source line, `lost` and `shift`). A line that finds
the queue full is not judged and is counted as such. The verdicts feed `dense.MeaningRate`, which loosens or
tightens that language's budget; every verdict, the rate with it and every adjustment go to the trace
(`live_meaning`, `live_budget_adjust`) and to the session's metrics.

The judge is a language model reached through `providers.get_judge`: the hosted model when one is configured (in a
GPU-engine session that is another model than the one that translated), else the session's own translator. It
does not go through the hosted voice account's one-request gate, so it never waits for, or delays, a voice line.
What it costs: one model call per judged batch (up to `BATCH` lines of one language).

What it is not: it judges a sample, not every line; it is a model's opinion, not a native speaker's; and in a
hosted-engine session the judge is of the same family as the translator.
"""
import asyncio
import logging
from collections.abc import Callable
from typing import Any

from app.config import Settings
from app.v1 import guards, trace
from app.v1.dense import MeaningRate

log = logging.getLogger("live.meaning")
BATCH = 4


class MeaningCheck:
    def __init__(self, llm: Any, sid: str, langs: list[str], s: Settings, *, now_ms: Callable[[], int],
                 behind: Callable[[str], bool]) -> None:
        self.llm, self.sid, self.s, self.now_ms, self.behind = llm, sid, s, now_ms, behind
        self.rates = {lg: MeaningRate(s.v1_meaning_window, s.v1_meaning_min_samples, s.v1_meaning_max,
                                      s.v1_meaning_low, s.v1_meaning_max_steps, s.v1_meaning_tighten_after_s)
                      for lg in langs}
        self._seen = {lg: [0, 0] for lg in langs}    # spoken lines seen: [budget off, budget on]
        self._q: asyncio.Queue[tuple[str, int, str, str, bool]] = asyncio.Queue(max(1, s.v1_meaning_queue))
        self.sampled = self.not_judged = self.no_verdict = 0
        self.adjustments: list[dict[str, Any]] = []
        self.usable = getattr(llm, "judge_lines", None) is not None

    def steps(self, lang: str) -> int:
        r = self.rates.get(lang)
        return r.steps if r is not None else 0

    def offer(self, lang: str, seq: int, src: str, out: str, budgeted: bool) -> bool:
        """A line that was just spoken. True when it was taken into the sample."""
        if not self.usable or lang not in self.rates or not src.strip() or not out.strip():
            return False
        n = self._seen[lang]
        n[int(budgeted)] += 1
        every = self.s.v1_meaning_sample_every if budgeted else self.s.v1_meaning_idle_every
        if every <= 0 or n[int(budgeted)] % every:
            return False
        try:
            self._q.put_nowait((lang, seq, src, out, budgeted))
        except asyncio.QueueFull:
            self.not_judged += 1
            return False
        self.sampled += 1
        return True

    async def run(self) -> None:
        """The worker: judges what is queued, one call at a time, until it is cancelled."""
        while True:
            first = await self._q.get()
            batch, keep = [first], []
            while len(batch) < BATCH and not self._q.empty():
                item = self._q.get_nowait()
                (batch if item[0] == first[0] else keep).append(item)
            for item in keep:
                self._q.put_nowait(item)
            lang = first[0]
            got = await guards.judge(self.llm, [(src, out) for _, _, src, out, _ in batch], lang,
                                     self.s.v1_meaning_timeout_s)
            if got is None:
                self.no_verdict += len(batch)
                continue
            for (_, seq, _, _, budgeted), v in zip(batch, got):
                self._note(lang, seq, budgeted, v)

    def _note(self, lang: str, seq: int, budgeted: bool, v: dict[str, bool]) -> None:
        r = self.rates[lang]
        change = r.add(budgeted=budgeted, lost=v["lost"], shift=v["shift"], now_s=self.now_ms() / 1000,
                       behind=self.behind(lang))
        rate = r.rate()
        if trace.enabled():
            trace.event("live_meaning", session=self.sid, seq=seq, lang=lang, budgeted=budgeted, lost=v["lost"],
                        shift=v["shift"], rate=round(rate, 3) if rate is not None else None, steps=r.steps)
        if change:
            self._adjusted(lang, change)

    def tick(self) -> None:
        """Once in a while without a verdict: the trial step back from "translated in full"."""
        for lang, r in self.rates.items():
            change = r.tick(self.now_ms() / 1000, self.behind(lang))
            if change:
                self._adjusted(lang, change)

    def _adjusted(self, lang: str, change: dict[str, Any]) -> None:
        rec = {"t_ms": self.now_ms(), "lang": lang, **change}
        self.adjustments.append(rec)
        del self.adjustments[:-200]
        log.warning("live %s %s: budget step %d -> %d (%s)", self.sid[:8], lang, change["was"], change["steps"], change["why"])
        if trace.enabled():
            trace.event("live_budget_adjust", session=self.sid, **rec)

    def stats(self) -> dict[str, Any]:
        return {"judge": trace.provider_name(self.llm) if self.usable else None, "sampled": self.sampled,
                "queue_full": self.not_judged, "no_verdict": self.no_verdict,
                "by_lang": {lg: r.state() for lg, r in self.rates.items()}, "adjustments": list(self.adjustments)}
