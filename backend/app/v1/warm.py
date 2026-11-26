"""One English voice for a whole Live session: the parts without I/O.

English is the one language our own voice engine does not speak, so its lines go to the hosted service: in the
hosted copy of the speaker's voice or in a stock voice. Chosen line by line (v0) a session changed voice about
nine times; here the voice is chosen once, at the session's start, and kept.

  en_mode     manual mode (`V1_EN_SINGLE_VOICE`): the setting `V1_EN_VOICE` as "copy" or "stock"
  en_choice   auto mode: the choice from a measurement at the session's start (a probe line in the copy, timed
              against the time a line has); see `LivePipeline._en_probe`

(The session-start warm-up, the stock voice matched to the speaker's pitch and the softened change of voice of
v1.1 were removed in v1.2: no proven gain in their measurements. docs/handbook/adr, "removed features".)
"""

# The probe: about the length of a live phrase (11 words), so its time is the time of a typical line.
EN_PROBE_LINE = "Okay, now let us see what happens in the next round."


def en_mode(setting: str) -> str:
    """Manual mode: "copy" or "stock" for the whole session. `auto` there is the stock voice: with every English
    line in the hosted copy, 73.7% of the lines started within 1 s of their moment against 87.2% in the stock
    voice (dense reel, 3 runs each, 25 Nov 2026; docs/v1/PROGRESS.md, v1.1 WS2)."""
    return "copy" if setting == "copy" else "stock"


def en_choice(probe_ms: int | None, available_ms: int, error: str = "") -> tuple[str, str]:
    """Auto mode: (voice, why). The copy when its probe line was there within the time a line has; else the one
    stock voice. `probe_ms` None = the copy did not answer (`error` says how)."""
    if probe_ms is None:
        return "stock", f"the copied voice did not answer the probe ({error or 'no sound'})"
    if probe_ms <= available_ms:
        return "copy", f"the copied voice made the probe line in {probe_ms} ms, within the {available_ms} ms a line has"
    return "stock", f"the copied voice took {probe_ms} ms for the probe line, more than the {available_ms} ms a line has"
