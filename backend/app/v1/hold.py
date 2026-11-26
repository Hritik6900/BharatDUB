"""Sync mode: the viewers' hold comes back down after it grew (`LIVE_SYNC_EASE`, the one switch for it).

The hold is how far behind the console's video a viewer's video is kept, so translation and voice have that long
to be ready (`live_sync_delay_ms`, 6 s). When phrases keep arriving after their moment it grows, one second at a
time (`LivePipeline._note_late`). It never came back: on a 67-minute stream it went from 6 s to 11 s during
stalls of the link and stayed there for the rest of the session (SPEC section 21).

The rule here, checked with every phrase that is spoken:
  * a phrase is "in time" when its sound was ready at least `step + spare` before its moment, so that one step
    less hold still leaves `spare`;
  * a phrase that was not (or that was skipped as too late, or a hold that just grew) is trouble: the count
    starts again;
  * the hold goes down one `step` when it is above its normal value, nothing was trouble for `calm_ms`, at least
    `min_phrases` phrases were in time since the last trouble, at least one since the last step, and the last
    step is `every_ms` old;
  * never under the value the session began with.
No phrases (the speaker is silent, or nothing is dubbed) means no evidence and no step.
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Ease:
    base_ms: int                # the hold the session began with; the hold is never eased under it
    step_ms: int = 250          # one step down
    every_ms: int = 5000        # at most one step in this long
    calm_ms: int = 20000        # nothing late for this long before the first step
    spare_ms: int = 500         # what a phrase must still have in hand after a step
    min_phrases: int = 3        # phrases in time since the last trouble
    steps: list[tuple[int, int]] = field(default_factory=list)   # (session ms, new hold) for every step down
    _trouble_at: int | None = None
    _good: int = 0
    _good_since_step: int = 0
    _last_step: int | None = None
    _last_key: Any = None

    def trouble(self, now_ms: int) -> None:
        """A late or skipped phrase, or the hold grew: the wait starts again."""
        self._trouble_at, self._good, self._good_since_step, self._last_key = now_ms, 0, 0, None

    def note(self, late_ms: int, now_ms: int, key: Any = None) -> None:
        """One spoken phrase. `late_ms`: how long after its moment its sound was ready (negative = before).
        A phrase spoken in several languages has one `key` and counts once when it was in time in each."""
        if late_ms > -(self.step_ms + self.spare_ms):
            self.trouble(now_ms)
        elif key is None or key != self._last_key:
            self._good += 1
            self._good_since_step += 1
            self._last_key = key

    def next(self, hold_ms: int, now_ms: int) -> int:
        """The hold to use from now on: `hold_ms`, or one step less."""
        if hold_ms <= self.base_ms:
            return hold_ms
        if self._trouble_at is None:    # above normal with nothing on record: count from here
            self._trouble_at = now_ms
        if now_ms - self._trouble_at < self.calm_ms or self._good < self.min_phrases or self._good_since_step < 1:
            return hold_ms
        if self._last_step is not None and now_ms - self._last_step < self.every_ms:
            return hold_ms
        new = max(self.base_ms, hold_ms - self.step_ms)
        self._last_step, self._good_since_step = now_ms, 0
        self.steps.append((now_ms, new))
        return new
