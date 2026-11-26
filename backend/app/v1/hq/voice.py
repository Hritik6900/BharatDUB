"""Studio HQ, phase C: several spoken versions of a line, each scored, the best one kept.

A line is spoken once and checked. A version that passes is kept at once: most lines need no more. A line that
fails gets more versions (up to `v1_hq_nbest`, from our voice engine, which draws a new random start every time,
and from the candidate voices of the routing file), then a shortened text when nothing fits, and is flagged for a
person to hear when it still fails.

The check of a version (`score`):
  backcheck   share of the line's words heard back by a speech-to-text (0-1)
  similarity  its voice against the speaker's sample, when the scorer measures it (else None)
  speed       how much it has to be sped up to fit its slot (1 = fits)
"""
import hashlib
import io
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import soundfile as sf

from app.config import Settings
from app.providers.base import ProviderError, VoiceSpec
from app.shared import audio_utils as au
from app.shared import cache
from app.studio.stages import fit
from app.studio.stages.voice import voice_id
from app.v1.qa import _words as _qa_words
from app.v1.qa import heard_share, rule_now
from app.v1.stages import StageFailed, Stages
from app.v1 import mode as v1mode

CACHE_VERSION = "hq-voice-1"


@dataclass
class Version:
    idx: int
    path: str                       # cached WAV of this version
    provider: str
    text: str
    engine_speed: float = 1.0       # the speed the voice itself was asked for
    dur_s: float = 0.0
    speed: float = 1.0              # speed-up still needed to fit the slot
    backcheck: float | None = None
    similarity: float | None = None
    heard: str = ""
    scored_by: str = ""
    passed: bool = False
    why: list[str] = field(default_factory=list)
    gpu_ms: float | None = None     # the voice engine's own time for this take, when it reported one
    passed_over: list[str] = field(default_factory=list)   # `V1_HQ_JUDGE`: judges that failed before `scored_by` answered
    rule: str = ""                  # the comparison rule the score was worked out with (qa.HEARD_RULE*)

    def rank(self, max_speed: float) -> float:
        """Higher is better: words understood first, then how far over the speed limit, then the voice."""
        over = max(0.0, self.speed - max_speed)
        return (self.backcheck if self.backcheck is not None else 0.5) - 0.6 * over + 0.1 * (self.similarity or 0.0)

    @property
    def only_too_long(self) -> bool:
        """Its words were understood; it just does not fit its slot. Another take will not help, fewer words will."""
        real = [w for w in self.why if not w.startswith("not checked")]
        return bool(real) and all(w.startswith("needs ") for w in real)

    def public(self, heard: bool = False) -> dict[str, Any]:
        """The take as it is stored with its line. `heard` keeps what the judge heard (the v1.1 judge and the
        calibration page work a score out again from it); the API never hands it out."""
        d = asdict(self)
        if not heard:
            d.pop("heard")
            d.pop("rule")
        if not d["passed_over"]:
            d.pop("passed_over")   # as before unless a judge was passed over
        return d


def _judges(st: Any, lang: str) -> list[str]:
    ask = getattr(st, "judges", None)
    return list(ask(lang)) if ask else list(st.names("score"))


def limits(s: Settings) -> tuple[float, float, float]:
    """(largest speed-up, least share of words heard back, least speaker similarity) for a version to pass."""
    return (s.v1_fit_max_speed if v1mode.on("fit_115", s) else fit.MAX_SPEED), s.v1_hq_backcheck_min, s.v1_hq_similarity_min


async def make(st: Stages, text: str, lang: str, vspec: VoiceSpec, *, idx: int, speed: float = 1.0,
               provider: str = "", usage: dict[str, Any]) -> Version:
    """Speak one version (or take it from the cache: same text, voice, speed and version number)."""
    own = st.own_voice(lang, vspec)
    speed = round(speed, 2) if own else 1.0
    key = au.cache_key(CACHE_VERSION, text, lang, voice_id(vspec), provider or "chain", st.mode, speed, idx,
                       st.r.s.tts_sample_rate)
    hit = cache.get_file("voice_hq", key, "wav")
    meta = cache.get_json("voice_hq", key)
    if hit and meta:
        usage["tts_cache_hits"] = usage.get("tts_cache_hits", 0) + 1
        return Version(idx, str(hit), meta["provider"], text, speed, au.duration_s(hit))   # from the cache: no GPU work now
    if provider:
        audio, used = await _candidate(st, provider, text, lang, vspec), provider
    else:
        audio = await st.speak(text, lang, vspec, speed=speed)
        used = st.used.get("speak", "")
    usage["tts_calls"] = usage.get("tts_calls", 0) + 1
    usage["tts_chars"] = usage.get("tts_chars", 0) + len(text)
    path = cache.put_file("voice_hq", key, "wav", audio)
    cache.put_json("voice_hq", key, {"provider": used})
    ask = getattr(st, "voice_engine_ms", None)
    gpu_ms = ask() if ask and used == "indicf5" else None
    return Version(idx, str(path), used, text, speed, au.duration_s(path), gpu_ms=gpu_ms)


async def _candidate(st: Stages, name: str, text: str, lang: str, vspec: VoiceSpec) -> bytes:
    """A line from one of the extra candidate voices (they take the same sample as our engine)."""
    emb = dict(vspec["embedding"]) if vspec["kind"] == "clone" else {}
    if not emb.get("ref_path"):
        raise ProviderError(f"{name}: needs a copied voice with a sample")
    from app.shared.voices import voices_dir
    voice = st.r.provider("voice", name)
    if not voice.speaks(lang):
        raise ProviderError(f"{name} does not speak {lang}")
    sid = "hq-" + hashlib.sha256(str(emb["ref_path"]).encode()).hexdigest()[:16]
    await voice.set_ref(sid, str(voices_dir() / emb["ref_path"]), emb["ref_text"], consent_at=emb.get("consent_at"))
    pcm, rate = await voice.synth(sid, text, lang)
    import numpy as np
    x = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    sr = st.r.s.tts_sample_rate
    if rate != sr:
        x = np.interp(np.linspace(0, len(x) - 1, int(len(x) * sr / rate)), np.arange(len(x)), x).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, x, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


async def score(st: Stages, v: Version, lang: str, slot_s: float, ref_wav: Path | None, s: Settings,
                usage: dict[str, Any]) -> Version:
    max_speed, min_check, min_sim = limits(s)
    v.speed = round(fit.needed_speed(v.dur_s, slot_s), 3)
    key = au.cache_key("hq-score-1", au.sha256_file(v.path), v.text, lang, str(ref_wav.name if ref_wav else ""),
                       ",".join(_judges(st, lang)))
    got = cache.get_json("score_hq", key)
    if got is None:
        try:
            got = await st.score(Path(v.path), v.text, lang, ref_wav)
            cache.put_json("score_hq", key, got)
            usage["score_calls"] = usage.get("score_calls", 0) + 1
        except StageFailed as e:
            got = {"backcheck": None, "similarity": None, "heard": "", "by": "", "error": str(e)[:160]}
    v.heard, v.scored_by = got.get("heard") or "", got.get("by") or ""
    v.passed_over = list(got.get("passed_over") or [])
    v.similarity = got.get("similarity")
    v.backcheck = got.get("backcheck")
    rule = v.rule = rule_now(s)
    if v.backcheck is not None and got.get("rule") != rule:
        # a score stored under another rule: worked out again from what was heard, without hearing again
        v.backcheck = round(heard_share(v.text, v.heard, rule), 3)
    v.why = []
    if v.backcheck is None:
        v.why.append("not checked: no scorer answered")
    elif v.backcheck < min_check:
        v.why.append(f"only {v.backcheck:.0%} of its words were heard back")
    if v.speed > max_speed + 0.005:
        v.why.append(f"needs {v.speed:.2f}x to fit its {slot_s:.1f} s")
    if min_sim > 0 and v.similarity is not None and v.similarity < min_sim:
        v.why.append(f"voice similarity {v.similarity:.2f} under {min_sim:.2f}")
    # A line nobody could check is not failed for it: it is spoken, and reported as unchecked.
    v.passed = not [w for w in v.why if not w.startswith("not checked")]
    return v


def take_plan(s: Settings) -> tuple[int, float | None, bool]:
    """(most takes of a line in our voice, the score under which another take is made or None for v1's rule
    "until one passes", every take is made regardless).

      as v1          up to `v1_hq_nbest`, until a take passes its whole check
      adaptive       one take; more, up to `v1_hq_adaptive_max`, only while the best score is under the threshold
      fixed          always `v1_hq_takes_fixed` takes (to measure what adaptive saves; not for normal use)
    """
    if s.v1_hq_takes_fixed > 0:
        return int(s.v1_hq_takes_fixed), None, True
    if v1mode.on("hq_adaptive", s):
        return max(1, int(s.v1_hq_adaptive_max)), float(s.v1_hq_adaptive_min or s.v1_hq_backcheck_min), False
    return max(1, int(s.v1_hq_nbest)), None, False


def heard_twice(made: list[Version]) -> bool:
    """Two takes of the same words at the same engine speed were heard back as exactly the same words."""
    seen: set[tuple[float, str, tuple[str, ...]]] = set()
    for v in made:
        if not v.heard.strip():
            continue
        key = (v.engine_speed, v.text, tuple(_qa_words(v.heard, True)))
        if key in seen:
            return True
        seen.add(key)
    return False


def pace_speed(v: Version, slot_s: float, s: Settings) -> float:
    """Duration control: the speed to ask the voice engine for so the line fits its slot, never under 300 ms a
    word and never over `gpu_voice_pace_max` (measured in v0: faster than that the engine loses words)."""
    need = fit.needed_speed(v.dur_s, slot_s)
    if need <= 1.03:
        return 1.0
    per_word = v.dur_s * 1000 / max(1, len(v.text.split()))
    return round(max(1.0, min(need, s.gpu_voice_pace_max, per_word / 300)), 2)


async def best_line(st: Stages, text: str, lang: str, vspec: VoiceSpec, slot_s: float, ref_wav: Path | None,
                    s: Settings, usage: dict[str, Any], *, edited: bool = False) -> tuple[Version, list[Version], bool]:
    """Returns (the version to use, every version made, flagged)."""
    max_speed, _, _ = limits(s)
    own = st.own_voice(lang, vspec)
    made: list[Version] = []

    async def add(t: str, speed: float = 1.0, provider: str = "") -> Version | None:
        try:
            v = await make(st, t, lang, vspec, idx=len(made), speed=speed, provider=provider, usage=usage)
        except (ProviderError, OSError, ValueError) as e:
            usage["tts_failed"] = usage.get("tts_failed", 0) + 1
            if not made and not provider:
                raise ProviderError(f"voice: {str(e)[:200]}") from e
            return None
        made.append(await score(st, v, lang, slot_s, ref_wav, s, usage))
        return made[-1]

    first = await add(text)
    assert first is not None
    if own and first.speed > 1.03:
        # Duration control first: the engine itself speaks faster, which sounds better than squeezing afterwards.
        speed = pace_speed(first, slot_s, s)
        if speed > 1.03:
            await add(text, speed=speed)
    engine_speed = max((v.engine_speed for v in made), default=1.0)
    most, need, fixed = take_plan(s)

    def another_take_helps() -> bool:
        if fixed:        # measurement: every take is made, whatever the first one scored
            return True
        if need is not None:   # `V1_HQ_ADAPTIVE`: more takes only while no take's words were heard back well enough
            if any(v.backcheck is None or v.backcheck >= need for v in made):
                return False
            # ... and, with `v1_hq_adaptive_same_stop`, not once two takes were heard as the very same words: then
            # it is mostly the wording or the judge's spelling that costs the points. Off by default: on the takes
            # of three videos it saved 16 of 145 takes and kept a lower-scored take on 3 of 76 lines.
            return not (s.v1_hq_adaptive_same_stop and heard_twice(made))
        return not any(v.passed or v.only_too_long for v in made)

    if another_take_helps():
        if own:   # the engine draws a new random start each time: another take is another chance
            while len(made) < most and another_take_helps():
                if await add(text, speed=engine_speed) is None:
                    break
        if fixed:
            pass     # the candidate voices are not part of a fixed count
        elif another_take_helps():
            for name in st.names("candidates"):
                if await add(text, provider=name) and made[-1].passed:
                    break
    best = max(made, key=lambda v: (v.passed, v.rank(max_speed)))
    if not best.passed and best.speed > max_speed and not edited:
        # Still too long for its slot: fewer words. (An edited line is the person's own wording and is left alone.)
        words = len(best.text.split())
        want = max(3, int(words * slot_s * max_speed / max(best.dur_s, 0.2) * 0.9))
        if want < words:
            try:
                shorter = (await st.llm("translate").shorten(best.text, lang, slot_s * 1.1, max_words=want)).strip()
            except Exception:  # noqa: BLE001 - the long version stays, flagged
                shorter = ""
            if shorter and len(shorter.split()) < words:
                usage["shortened"] = usage.get("shortened", 0) + 1
                await add(shorter, speed=engine_speed if own else 1.0)
                best = max(made, key=lambda v: (v.passed, v.rank(max_speed)))
    return best, made, not best.passed
