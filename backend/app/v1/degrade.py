"""The Live degradation ladder (`V1_LIVE_DEGRADE`): a session steps down when a service dies and back up when it
answers again. It never ends because a provider died.

  0 copied     the speaker's copied voice
  1 stock      a stock voice (the copied voice's engine is away, or the session never had one)
  2 captions   no voice answers: captions only, viewers see "audio returning shortly"
  3 original   no translation or no transcript: viewers hear the stream's own sound

The ladder only counts what the pipeline tells it: `note(kind, ok)` after every try of a copied voice, a stock
voice, a translation, the speech-to-text stream. `fails` failures in a row put a kind down; one success brings it
back. While a kind is down it is still tried, but only once every `probe_ms` (`may_try`), so a dead service does
not hold every phrase for its timeout.
"""
from collections.abc import Callable

RUNGS = ("copied", "stock", "captions", "original")
KINDS = ("copied", "stock", "translate", "stt")


class Ladder:
    def __init__(self, clock: Callable[[], int], *, fails: int = 2, probe_ms: int = 10000) -> None:
        self.clock, self.fails, self.probe_ms = clock, max(1, fails), probe_ms
        self._failed = dict.fromkeys(KINDS, 0)
        self._tried: dict[str, int] = {}

    def note(self, kind: str, ok: bool) -> None:
        self._failed[kind] = 0 if ok else self._failed[kind] + 1

    def down(self, kind: str) -> bool:
        return self._failed[kind] >= self.fails

    def may_try(self, kind: str) -> bool:
        """Always while the kind is up; while it is down, once every `probe_ms` (that try is the way back up)."""
        if not self.down(kind):
            return True
        now = self.clock()
        if kind not in self._tried or now - self._tried[kind] >= self.probe_ms:
            self._tried[kind] = now
            return True
        return False

    def level(self, *, wants_copied: bool, copied_ready: bool, copied_up: bool) -> tuple[int, str]:
        """(rung, why it is not the best one). `copied_ready`: the session has its voice; `copied_up`: the engine
        that speaks it is answering as far as the pipeline and the breakers know."""
        if self.down("stt"):
            return 3, "speech-to-text does not answer"
        if self.down("translate"):
            return 3, "translation does not answer"
        if wants_copied and copied_ready and copied_up and not self.down("copied"):
            return 0, ""
        if self.down("stock"):
            return 2, "no voice answers"
        if not wants_copied:
            return 1, ""
        return 1, "the copied voice is not ready yet" if not copied_ready else "the copied voice's engine does not answer"
