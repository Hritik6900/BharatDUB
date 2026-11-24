"""Studio HQ (`V1_STUDIO_HQ`, a job created with quality=hq): the same job, stores and outputs as Studio, with more
work per line. Three phases, so that several jobs can share the GPU one kind of model at a time:

  A  audio  extract, separate, segment, first hearing (all as v0, cached), further hearings by the other
            speech-to-text providers, who speaks when
  B  text   merge the hearings, clean the transcript, translate with a word limit per line, review, write
            numbers and symbols as words
  C  voice  per line: speak, check, more versions when it fails, pick the best, flag what still fails; then the
            mix (sidechain ducking, loudness) and the render

`run_job` does A, B, C for one job. `run_batch` does A for every job, then B for every job, then C: with a big
translation model that is loaded once per HQ window, that is one load for the whole night's videos.

Every provider comes from the `studio_hq` lists of config/routing.yaml. A server that is not there is skipped:
without the big model the small one or the hosted one translates, without a second speech-to-text there is one
hearing, without the QA server the hosted speech-to-text hears the lines back and no similarity is measured.
"""
import asyncio
import logging
from pathlib import Path
from typing import Any

from app.providers.base import ProviderError
from app.shared import audio_utils as au
from app.shared import cache
from app.studio.stages import fit
from app.v1 import trace
from app.v1.hq import glossary as hqgloss
from app.v1.hq import normalise as hqnorm
from app.v1.hq import review as hqreview
from app.v1.hq import text as hqtext
from app.v1.hq import voice as hqvoice
from app.v1.stages import StageFailed, Stages

log = logging.getLogger("studio.hq")
STOCK_PACE_MS = 400.0     # ms a word assumed for a stock voice until it is measured in this job


def is_hq(meta: dict[str, Any], settings: Any) -> bool:
    return bool(settings.v1_studio_hq and meta.get("quality") == "hq")


def stages_for(job_id: str, engine: str | None) -> Stages:
    return Stages("studio_hq", engine or "cloud", key=job_id)


# ---------- phase A ----------
async def phase_a(r: Any, ctx: Any, meta: dict[str, Any], st: Stages) -> None:
    await r._prepare(ctx, meta)   # v0's stages 2-5, unchanged and cached
    segs = await r.store.select("segments", order="idx", job_id=ctx.job_id)
    job = await r.store.get("jobs", ctx.job_id) or {}
    lang = job.get("src_lang") or "hi-IN"
    others = st.names("transcribe")[1:]          # the first provider already heard every clip in `_prepare`
    async with r._stage(ctx, "hear_again"):
        for seg in segs:
            if not (seg.get("src_text") or "").strip() or not others:
                continue
            clip = ctx.dir / "clips" / f"src_{seg['idx']:03}.wav"
            if not clip.exists():
                continue
            key = au.cache_key("hq-hear-1", au.sha256_file(clip), lang, ",".join(others))
            heard = cache.get_json("transcribe_hq", key)
            if heard is None:
                heard = {}
                for name in others:
                    try:
                        res = await asyncio.wait_for(st.r.provider("stt", name).transcribe(str(clip), lang),
                                                     st.r.timeout("transcribe"))
                        if (res.text or "").strip():
                            heard[name] = res.text.strip()
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:  # noqa: BLE001 - one hearing fewer
                        st.fallbacks.append({"stage": "transcribe", "provider": name, "reason": str(e)[:140], "next": ""})
                cache.put_json("transcribe_hq", key, heard)
                ctx.usage["hq_hearings"] = ctx.usage.get("hq_hearings", 0) + len(heard)
            if heard:
                await r.store.update("segments", seg["id"], {"hearings": heard})
    async with r._stage(ctx, "speakers"):
        v16 = ctx.dir / "vocals16k.wav"
        turns: list[dict[str, Any]] = []
        if v16.exists() and st.names("diarize") and st.names("diarize") != ["none"]:
            key = au.cache_key("hq-diar-1", au.sha256_file(v16), ",".join(st.names("diarize")))
            got = cache.get_json("diarize_hq", key)
            if got is None:
                try:
                    got = await st.diarize(v16)
                    cache.put_json("diarize_hq", key, got)
                except StageFailed as e:
                    r._warn(ctx, f"Could not tell the speakers apart; treated as one speaker ({e})"[:300])
                    got = []
            turns = got
        speakers = {t["speaker"] for t in turns}
        if len(speakers) > 1:
            for seg in segs:
                seg_speaker = speaker_of(seg["start_s"], seg["end_s"], turns)
                if seg_speaker:
                    await r.store.update("segments", seg["id"], {"speaker": seg_speaker})
            r._warn(ctx, f"{len(speakers)} speakers were found. This version dubs them all in one voice.")
        meta.setdefault("hq", {})["speakers"] = len(speakers) or 1
    r._write_meta(ctx.dir, meta)


def speaker_of(start: float, end: float, turns: list[dict[str, Any]]) -> str | None:
    """The speaker who talks for most of [start, end]."""
    share: dict[str, float] = {}
    for t in turns:
        overlap = min(end, float(t["end"])) - max(start, float(t["start"]))
        if overlap > 0:
            share[t["speaker"]] = share.get(t["speaker"], 0.0) + overlap
    return max(share, key=lambda k: share[k]) if share else None


# ---------- phase B ----------
async def phase_b(r: Any, ctx: Any, meta: dict[str, Any], st: Stages, langs: list[str]) -> None:
    glossary = await r.glossary()
    segs = await r.spoken_segments(ctx.job_id)
    if not segs:
        return
    hq = meta.setdefault("hq", {})
    if r.s.v1_hq_auto_glossary:
        # Names, brands and repeated English terms of this video, found in its first hearing: this job's glossary.
        if "glossary_auto" not in hq:
            first = [s.get("src_text_raw") or s["src_text"] for s in segs]
            hq["glossary_auto"] = hqgloss.candidates(first, known=glossary, limit=r.s.v1_hq_auto_glossary_max)
            r._write_meta(ctx.dir, meta)
        glossary = list(dict.fromkeys([*glossary, *hqgloss.terms(hq["glossary_auto"])]))
    if not hq.get("text_done"):
        async with r._stage(ctx, "clean"):
            raw = [s.get("src_text_raw") or s["src_text"] for s in segs]
            lines = raw
            hearings = [dict(s.get("hearings") or {}) for s in segs]
            try:
                if any(hearings):
                    lines = await hqtext.merge_hearings(st, [{"first": t, **h} for t, h in zip(raw, hearings)], raw, glossary)
                    hq["merged_lines"] = sum(1 for a, b in zip(raw, lines) if a != b)
                cleaned = await hqtext.cleanup(st, lines, glossary)
                hq["cleaned_lines"] = sum(1 for a, b in zip(lines, cleaned) if a != b)
                lines = cleaned
                if r.s.v1_hq_review:   # a cleaned line that is no longer the line that was heard is put back
                    kept = [c if c == o or hqreview.keeps_source(o, c) else o for o, c in zip(raw, lines)]
                    hq["transcript_put_back"] = sum(1 for a, b in zip(lines, kept) if a != b)
                    lines = kept
            except StageFailed as e:
                r._warn(ctx, f"The transcript was not cleaned ({e})"[:300])
            for s, old, new in zip(segs, raw, lines):
                if new != s["src_text"] or not s.get("src_text_raw"):
                    await r.store.update("segments", s["id"], {"src_text": new, "src_text_raw": old})
            hq["text_done"] = True
            r._write_meta(ctx.dir, meta)
        segs = await r.spoken_segments(ctx.job_id)
    slots = fit.slots([s["start_s"] for s in segs], meta["duration"])
    for lang in langs:
        existing = {t["segment_id"]: t for t in await r.store.select_in(
            "translations", "segment_id", [s["id"] for s in segs], lang=lang)}
        todo = [(s, sl) for s, sl in zip(segs, slots) if not existing.get(s["id"], {}).get("edited")]
        if not todo:
            continue
        async with r._stage(ctx, "translate", lang):
            vspec = await r.voice_spec(ctx, lang)
            native = st.own_voice(lang, vspec)
            pace = float(r.s.gpu_voice_pace_ms or 450) if native else STOCK_PACE_MS
            src = [s["src_text"] for s, _ in todo]
            limits = [hqtext.word_limit(sl, s["end_s"] - s["start_s"], len(s["src_text"].split()), pace) for s, sl in todo]
            extra = [f for f in ("v1_hq_review", "v1_hq_normalise", "v1_hq_auto_glossary") if getattr(r.s, f)]
            first = [s.get("src_text_raw") or s["src_text"] for s, _ in todo]
            key = au.cache_key(hqtext.PROMPT_VERSION, src, limits, lang, sorted(glossary), native,
                               ",".join(st.names("translate")), ",".join(st.names("review")),
                               *([extra, first] if extra else []))   # with the v1.1 flags off: the key it always had
            out = cache.get_json("translate_hq", key)
            if out is None or len(out) != len(src):
                out = await translate_lines(r, ctx, st, src, limits, lang, glossary, native, hq, first=first)
                cache.put_json("translate_hq", key, out)
            for (s, _), line in zip(todo, out):
                if s["id"] in existing:
                    await r.store.update("translations", existing[s["id"]]["id"], {"text": line})
                else:
                    await r.store.insert("translations", {"segment_id": s["id"], "lang": lang, "text": line})
    r._write_meta(ctx.dir, meta)


async def translate_lines(r: Any, ctx: Any, st: Stages, src: list[str], limits: list[int], lang: str,
                          glossary: list[str], native: bool, hq: dict[str, Any], *,
                          first: list[str] | None = None) -> list[str]:
    s = r.s
    try:
        out = await hqtext.translate_timed(st, src, limits, lang, glossary, native,
                                           terms=glossary if s.v1_hq_auto_glossary else None)
    except StageFailed:
        out = None
    ctx.usage["llm_calls"] = ctx.usage.get("llm_calls", 0) + 1
    if out is None:   # the plain batch translation every provider has, as v0
        out = await st.llm("translate").translate_batch(src, lang, glossary)
        ctx.usage["llm_calls"] = ctx.usage.get("llm_calls", 0) + 1
    out = list(out)
    for i, line in enumerate(out):   # a line in the wrong script, or empty, is asked for again on its own
        if not hqtext.acceptable(line, lang, native):
            try:
                out[i] = await st.llm("translate").translate_chunk(src[i], lang, glossary, src[max(0, i - 2): i],
                                                                   native=native, max_words=limits[i])
                ctx.usage["llm_calls"] = ctx.usage.get("llm_calls", 0) + 1
            except (ProviderError, TimeoutError):
                pass
    stats = hq.setdefault(f"text:{lang}", {})
    try:
        if s.v1_hq_review:     # the hosted model against the written rubric; every edit is logged (hq/review.py)
            out, stats["review"] = await hqreview.review(st, src, out, limits, lang, glossary, native,
                                                         heard=first, job_id=ctx.job_id)
            stats["reviewed_changed"] = stats["review"]["edited"]
            if stats["review"].get("error"):
                r._warn(ctx, f"The {lang} translation was not reviewed ({stats['review']['error']})"[:300])
        else:
            out, stats["reviewed_changed"] = await hqtext.review(st, src, out, limits, lang, glossary, native)
        if s.v1_hq_normalise and hqnorm.covered(lang):   # by rule first; the model only sees what the rules left
            out, stats["normalised_by_rule"] = hqnorm.spoken_lines(out, lang, native)
        out, stats["normalised"] = await hqtext.normalise(st, out, lang, native)
        ctx.usage["llm_calls"] = ctx.usage.get("llm_calls", 0) + 2
    except StageFailed as e:
        r._warn(ctx, f"The {lang} translation was not reviewed ({e})"[:300])
    stats["over_limit"] = sum(1 for line, m in zip(out, limits) if len(line.split()) > m)
    return out


# ---------- phase C ----------
async def phase_c(r: Any, ctx: Any, meta: dict[str, Any], st: Stages, lang: str) -> None:
    segs = await r.spoken_segments(ctx.job_id)
    trs = {t["segment_id"]: t for t in await r.store.select_in(
        "translations", "segment_id", [s["id"] for s in segs], lang=lang)}
    vspec = await r.voice_spec(ctx, lang)
    ref_wav = sample_of(vspec)
    slots = fit.slots([s["start_s"] for s in segs], meta["duration"])
    max_speed = hqvoice.limits(r.s)[0]
    lines_dir = ctx.dir / "lines"
    lines_dir.mkdir(exist_ok=True)
    flagged = 0
    for seg, slot_s in zip(segs, slots):
        tr = trs.get(seg["id"])
        if not tr:
            continue
        async with r._stage(ctx, "voice", lang):
            try:
                best, made, flag = await hqvoice.best_line(st, tr["text"], lang, vspec, slot_s, ref_wav, r.s,
                                                           ctx.usage, edited=bool(tr.get("edited")))
            except ProviderError as e:
                if vspec["kind"] != "clone":
                    raise
                # The copied voice failed for this line: the stock voice speaks it, as v0 does.
                r._warn(ctx, f"Cloned voice failed for a {lang} line, used stock voice: {str(e)[:120]}")
                from app.studio.stages.voice import stock_voice
                best, made, flag = await hqvoice.best_line(st, tr["text"], lang, stock_voice(lang), slot_s, None,
                                                           r.s, ctx.usage, edited=bool(tr.get("edited")))
        async with r._stage(ctx, "fit", lang):
            out = lines_dir / f"{lang}_{seg['idx']:03}.wav"
            speed = await asyncio.to_thread(fit.fit_clip, Path(best.path), slot_s, out, max_speed)
        flagged += int(flag)
        fields = {"text": best.text, "audio_path": str(out.relative_to(ctx.dir)), "fit_speed": speed,
                  "flagged": flag, "flag_reason": "; ".join(best.why) if flag else "",
                  "qa": {"backcheck": best.backcheck, "similarity": best.similarity, "by": best.scored_by,
                         "provider": best.provider, **({"passed_over": best.passed_over} if best.passed_over else {})},
                  "alts": [v.public(heard=bool(r.s.v1_hq_judge or r.s.v1_hq_calibrate)) for v in made], "picked": best.idx}
        await r.store.update("translations", tr["id"], fields)
        if r.s.v1_trace:
            trace.studio_line(ctx.job_id, lang, seg["idx"], mode="studio_hq", words=len(best.text.split()),
                              slot_s=round(slot_s, 3), dur_s=round(best.dur_s, 3), speed=speed,
                              native_speed=best.engine_speed, tts=best.provider, clone=vspec["kind"] == "clone",
                              backcheck=best.backcheck, similarity=best.similarity, scored_by=best.scored_by,
                              judge_passed_over=best.passed_over or None,
                              versions=len(made), flagged=flag, fallback=best.provider not in ("indicf5", "timbre") or
                              (vspec["kind"] == "clone" and best.provider == "timbre" and st.own_voice(lang, vspec)),
                              shortened=best.text != tr["text"],
                              gpu_s=round(sum(v.gpu_ms for v in made if v.gpu_ms) / 1000, 3) if any(v.gpu_ms for v in made) else None)
    meta.setdefault("hq", {})[f"flagged:{lang}"] = flagged
    r._write_meta(ctx.dir, meta)
    await r._mix_render(ctx, meta, lang)


def sample_of(vspec: Any) -> Path | None:
    """The speaker's own sample for a copied voice (to compare the dub's voice with), if there is one on disk."""
    if vspec["kind"] != "clone":
        return None
    ref = dict(vspec["embedding"]).get("ref_path")
    if not ref:
        return None
    from app.shared.voices import voices_dir
    p = voices_dir() / str(ref)
    return p if p.exists() else None


# ---------- one job, and several jobs phase by phase ----------
async def run_job(r: Any, ctx: Any, meta: dict[str, Any], job: dict[str, Any], engine: str | None) -> None:
    st = stages_for(ctx.job_id, engine)
    await phase_a(r, ctx, meta, st)
    await phase_b(r, ctx, meta, st, job["target_langs"])
    for lang in job["target_langs"]:
        await phase_c(r, ctx, meta, st, lang)
    note_fallbacks(r, ctx, st)


async def add_langs(r: Any, ctx: Any, meta: dict[str, Any], langs: list[str], engine: str | None) -> None:
    """More languages for a finished HQ job: phases B and C for them; the audio work is not repeated."""
    st = stages_for(ctx.job_id, engine)
    await phase_b(r, ctx, meta, st, langs)
    for lang in langs:
        await phase_c(r, ctx, meta, st, lang)
    note_fallbacks(r, ctx, st)


def note_fallbacks(r: Any, ctx: Any, st: Stages) -> None:
    if st.fallbacks:
        steps = sorted({f"{f['stage']} ({f['provider']})" for f in st.fallbacks})
        r._warn(ctx, "A fallback answered for: " + ", ".join(steps))
        ctx.usage["fallbacks"] = ctx.usage.get("fallbacks", 0) + len(st.fallbacks)


async def pick_alt(r: Any, ctx: Any, meta: dict[str, Any], tr: dict[str, Any], seg: dict[str, Any], alt: int) -> dict[str, Any]:
    """The editor's one-click swap: use another version of a line that was already made and scored."""
    alts = list(tr.get("alts") or [])
    chosen = next((a for a in alts if a.get("idx") == alt), None)
    if chosen is None or not Path(chosen["path"]).is_file():
        raise KeyError("no such version of this line")
    segs = await r.spoken_segments(ctx.job_id)
    slots = fit.slots([s["start_s"] for s in segs], meta["duration"])
    slot_s = next(sl for s, sl in zip(segs, slots) if s["id"] == seg["id"])
    out = ctx.dir / "lines" / f"{tr['lang']}_{seg['idx']:03}.wav"
    speed = await asyncio.to_thread(fit.fit_clip, Path(chosen["path"]), slot_s, out, hqvoice.limits(r.s)[0])
    fields = {"text": chosen["text"], "audio_path": str(out.relative_to(ctx.dir)), "fit_speed": speed,
              "picked": alt, "flagged": False, "flag_reason": "", "picked_by_hand": True,
              "qa": {"backcheck": chosen.get("backcheck"), "similarity": chosen.get("similarity"),
                     "by": chosen.get("scored_by"), "provider": chosen.get("provider")}}
    row = await r.store.update("translations", tr["id"], fields) or {**tr, **fields}
    await r._mix_render(ctx, meta, tr["lang"])
    return row

