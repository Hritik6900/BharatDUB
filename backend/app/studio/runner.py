"""Studio job state machine: stages 1-10 with per-stage cache, timings, events and partial re-render."""
import asyncio
import json
import logging
import shutil
from collections import Counter, defaultdict
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.config import DEFAULT_GLOSSARY, Settings, get_settings
from app.db import Store, get_store, now_iso
from app.providers import get_judge, get_llm, get_stt, get_tts
from app.providers.base import LLM, STT, TTS, ProviderError, VoiceSpec
from app.shared import audio_utils as au
from app.shared import cache
from app.shared.metrics import StageTimer
from app.shared.storage import publish_output
from app.studio.events import events
from app.v1 import apilog
from app.studio.stages import extract, fit, mix, render, segment, separate, transcribe, translate, voice
from app.v1 import guards, lineguard, trace
from app.v1.hq import runner as hq
from app.v1 import mode as v1mode

log = logging.getLogger("studio")
# The engine of the job being worked on in this task: None = the hosted services (as before), "gpu" = our own machine.
ENGINE: ContextVar[str | None] = ContextVar("studio_engine", default=None)
# v1: which provider lists the router uses for this job (`studio`, or `studio_hq` for an HQ job).
MODE: ContextVar[str] = ContextVar("studio_mode", default="studio")

STAGES = ["ingest", "extract", "separate", "segment", "transcribe", "translate", "voice", "fit", "mix", "render"]


@dataclass
class Ctx:
    job_id: str
    dir: Path
    timer: StageTimer = field(default_factory=StageTimer)
    usage: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    guards: dict[str, dict[str, int]] = field(default_factory=dict)   # v1.2: per language, what the guards found


class StudioRunner:
    def __init__(self, store: Store | None = None, stt: STT | None = None, llm: LLM | None = None,
                 tts: TTS | None = None, settings: Settings | None = None) -> None:
        self.s = settings or get_settings()
        self._store, self._stt, self._llm, self._tts = store, stt, llm, tts
        self._tasks: set[asyncio.Task[Any]] = set()
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        # (job, lang) -> (source lines, running translation). See _pretranslate.
        self._ahead: dict[tuple[str, str], tuple[list[str], asyncio.Task[list[str]]]] = {}

    # Lazy so the app can start without keys.
    @property
    def store(self) -> Store:
        return self._store or get_store()

    # Each job runs in its own task, and `ENGINE` says which engine that job asked for (None = the hosted services
    # as before). A context variable, so two jobs with different engines can run side by side.
    @property
    def stt(self) -> STT:
        return self._stt or get_stt(ENGINE.get() or None, mode=MODE.get())

    @property
    def llm(self) -> LLM:
        return self._llm or get_llm(ENGINE.get() or None, mode=MODE.get())

    @property
    def tts(self) -> TTS:
        return self._tts or get_tts(ENGINE.get() or None, mode=MODE.get())

    def job_engine(self, job_id: str) -> str:
        """Which engine a job was made with: `cloud` (the hosted services) or `gpu`."""
        try:
            return "gpu" if self._meta(self.job_dir(job_id)).get("engine") == "gpu" else "cloud"
        except (OSError, ValueError):
            return "cloud"

    def _use_engine(self, job_dir: Path) -> None:
        try:
            ENGINE.set(self._meta(job_dir).get("engine") or None)
        except (OSError, ValueError):
            ENGINE.set(None)

    def job_dir(self, job_id: str) -> Path:
        return self.s.data_path / "jobs" / job_id

    # ---------- create ----------
    async def create_job(self, upload: Path, source_name: str, target_langs: list[str],
                         voice_profile_id: str | None = None,
                         voice_from_video: dict[str, str] | None = None, engine: str | None = None,
                         quality: str | None = None) -> dict[str, Any]:
        """Stage 1 (ingest). Raises extract.IngestError with a user-facing message."""
        duration = await asyncio.to_thread(extract.ingest, upload, self.s.max_video_seconds)
        expires = datetime.now(timezone.utc) + timedelta(hours=self.s.upload_ttl_hours)
        job = await self.store.insert("jobs", {
            "source_path": source_name, "duration_s": round(duration, 3), "target_langs": target_langs,
            "voice_profile_id": voice_profile_id, "status": "queued", "stage": "ingest",
            "expires_at": expires.isoformat(),
        })
        d = self.job_dir(job["id"])
        d.mkdir(parents=True, exist_ok=True)
        shutil.move(str(upload), d / f"source{upload.suffix.lower() or '.mp4'}")
        self._write_meta(d, {"source": f"source{upload.suffix.lower() or '.mp4'}",
                             "name": Path(source_name).stem[:60] or "video", "duration": duration,
                             "voice_from_video": voice_from_video,
                             **({"engine": "gpu"} if engine == "gpu" else {}),
                             **({"quality": "hq"} if quality == "hq" else {})})   # v1: the HQ path
        return job

    def start(self, job_id: str) -> asyncio.Task[Any]:
        task = asyncio.create_task(self.run(job_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    # ---------- full run ----------
    async def run(self, job_id: str) -> None:
        apilog.set_test("job", job_id)
        ctx = Ctx(job_id, self.job_dir(job_id))
        self._use_engine(ctx.dir)
        job = await self.store.get("jobs", job_id)
        if not job:
            return
        meta = self._meta(ctx.dir)
        ctx.timer.timings["ingest"] = 0.0
        await self._set(ctx, status="running")
        try:
            async with self._locks[job_id]:
                if hq.is_hq(meta, self.s):   # v1: more work per line (docs/v1/ARCHITECTURE.md), same job and outputs
                    MODE.set("studio_hq")
                    await hq.run_job(self, ctx, meta, job, ENGINE.get())
                else:
                    await self._prepare(ctx, meta)
                    await self._pretranslate(ctx, job["target_langs"])
                    for lang in job["target_langs"]:
                        await self._process_lang(ctx, meta, lang)
            await self._set(ctx, status="done", stage=None)
        except Exception as e:  # noqa: BLE001 - job failure must be reported, not raised
            log.exception("job %s failed", job_id)
            await self._set(ctx, status="failed", error=_user_error(e))
        finally:
            self._drop_ahead(job_id)
            await self._save_stats(ctx)
            if v1mode.on("trace", self.s):
                gpu = ENGINE.get() == "gpu"
                trace.studio_job(job_id, mode="studio", engine=ENGINE.get() or "cloud", duration_s=job.get("duration_s"),
                                 langs=job.get("target_langs"), total_s=round(sum(v for k, v in ctx.timer.timings.items() if ":" not in k), 3),
                                 stages={k: v for k, v in ctx.timer.timings.items() if ":" not in k}, usage=dict(ctx.usage),
                                 stt_hosted=self.s.gpu_stt_first == "hosted" or not gpu, llm_hosted=not gpu, tts_hosted=not gpu,
                                 warnings=len(ctx.warnings))
            events.publish(job_id, {"type": "end", "job": await self.store.get("jobs", job_id)})

    async def _prepare(self, ctx: Ctx, meta: dict[str, Any]) -> None:
        d = ctx.dir
        full = d / "full.wav"
        async with self._stage(ctx, "extract"):
            if not full.exists():
                await asyncio.to_thread(extract.extract, d / meta["source"], full)
            meta["audio_hash"] = await asyncio.to_thread(au.sha256_file, full)

        async with self._stage(ctx, "separate"):
            vocals, background = full, None
            if self.s.studio_separate:
                try:
                    vocals, background = await asyncio.to_thread(separate.separate, full, meta["audio_hash"])
                except Exception as e:  # noqa: BLE001
                    self._warn(ctx, f"Background separation failed, dubbing without background music ({e})"[:300])
            meta["vocals"], meta["background"] = str(vocals), str(background) if background else None

        async with self._stage(ctx, "segment"):
            v16 = d / "vocals16k.wav"
            await asyncio.to_thread(au.extract_wav, vocals, v16, 16000)
            key = au.cache_key(await asyncio.to_thread(au.sha256_file, v16), segment.MAX_LEN, segment.MIN_GAP)
            segs = cache.get_json("segment", key)
            if segs is None:
                try:
                    segs = await asyncio.to_thread(segment.segment, v16)
                    cache.put_json("segment", key, segs)
                except Exception as e:  # noqa: BLE001
                    self._warn(ctx, f"Speech detection failed, using 20 s windows ({e})"[:300])
                    segs = segment.fixed_windows(meta["duration"])
            segs = [tuple(s) for s in segs]
            if not segs:
                raise PipelineError("No speech found in this video.")
        await self._voice_from_video(ctx, meta, Path(vocals), segs)

        async with self._stage(ctx, "transcribe"):
            audio16 = await asyncio.to_thread(au.load_mono, v16, 16000)
            clips = await asyncio.to_thread(transcribe.cut_clips, audio16, segs, d / "clips")
            glossary = await self.glossary()
            results = await transcribe.transcribe_all(self.stt, clips, "indic-auto", glossary,
                                                      ctx.usage, ctx.warnings)
            if not any(r["text"] for r in results):
                why = f" ({ctx.warnings[-1].split(': ', 1)[-1]})" if ctx.warnings else ""
                raise PipelineError(f"Could not transcribe any speech in this video.{why}")
            langs = Counter(r["lang"] for r in results if r["lang"])
            src_lang = langs.most_common(1)[0][0] if langs else "indic-auto"
            await self.store.delete("segments", job_id=ctx.job_id)
            await self.store.insert_many("segments", [
                {"job_id": ctx.job_id, "idx": i, "start_s": s, "end_s": e, "src_text": r["text"],
                 "cache_key": au.cache_key(meta["audio_hash"], s, e)}
                for i, ((s, e), r) in enumerate(zip(segs, results))
            ])
            await self.store.update("jobs", ctx.job_id, {"src_lang": src_lang})
        self._write_meta(d, meta)

    async def _voice_from_video(self, ctx: Ctx, meta: dict[str, Any], vocals: Path,
                                segs: list[tuple[float, float]]) -> None:
        """Copy the voice heard in the video itself, if the uploader consented at upload (golden rule 4).

        Creates a normal voice profile (with consent_at) and attaches it to the job, so every later stage,
        added languages and Live sessions use it like any other profile. Fails soft to a stock voice.
        """
        consent = meta.get("voice_from_video") or {}
        if not consent.get("consent_at"):
            return
        job = await self.store.get("jobs", ctx.job_id) or {}
        if job.get("voice_profile_id"):
            return
        async with self._stage(ctx, "clone"):
            try:
                sample = ctx.dir / "voice_sample.wav"
                secs = await asyncio.to_thread(voice.build_sample, vocals, segs, sample)
                if secs < voice.SAMPLE_MIN_S:
                    self._warn(ctx, f"Only {secs:.0f} s of speech in this video, too little to copy the voice. "
                                    "Using a stock voice.")
                    return
                key = au.cache_key(await asyncio.to_thread(au.sha256_file, sample))
                emb = cache.get_json("clone", key)
                if emb is None:
                    emb = await self.tts.clone_embedding(str(sample), consent_at=consent["consent_at"])
                    cache.put_json("clone", key, emb)
                    ctx.usage["clone_calls"] = ctx.usage.get("clone_calls", 0) + 1
                profile = await self.store.insert("voice_profiles", {
                    "display_name": f"Voice from {meta['name']}"[:60], "embedding": emb,
                    "consent_text": consent.get("consent_text", ""), "consent_at": consent["consent_at"],
                })
                await self.store.update("jobs", ctx.job_id, {"voice_profile_id": profile["id"]})
            except (ProviderError, au.FFmpegError, OSError, ValueError) as e:
                self._warn(ctx, f"Could not copy the voice from this video; using a stock voice ({e})"[:300])

    # ---------- per language ----------
    async def _pretranslate(self, ctx: Ctx, langs: list[str]) -> None:
        """Start the translation of every language now, instead of one language after the other.

        Voice lines queue behind the one-request Gnani gate, but the LLM does not: while the first language
        is being voiced, the others are already translated. Each language's translate stage then waits for
        its own task, so stage order, events, cache and results are unchanged.
        """
        if not self.s.studio_translate_ahead or len(langs) < 2:
            return
        segs = await self.spoken_segments(ctx.job_id)
        glossary = await self.glossary()
        model = self.s.llm_model or "unset"
        for lang in langs:
            done = {t["segment_id"]: t for t in await self.store.select_in(
                "translations", "segment_id", [s["id"] for s in segs], lang=lang)}
            lines = [s["src_text"] for s in segs if not done.get(s["id"], {}).get("edited")]
            if not lines:
                continue
            task = asyncio.create_task(translate.translate(self.llm, lines, lang, glossary, model, ctx.usage))
            task.add_done_callback(lambda t: t.cancelled() or t.exception())  # read later, or not at all
            self._ahead[(ctx.job_id, lang)] = (lines, task)

    def _drop_ahead(self, job_id: str) -> None:
        for key in [k for k in self._ahead if k[0] == job_id]:
            self._ahead.pop(key)[1].cancel()

    async def _process_lang(self, ctx: Ctx, meta: dict[str, Any], lang: str) -> None:
        segs = await self.spoken_segments(ctx.job_id)
        existing = {t["segment_id"]: t for t in await self.store.select_in(
            "translations", "segment_id", [s["id"] for s in segs], lang=lang)}

        async with self._stage(ctx, "translate", lang):
            todo = [s for s in segs if not existing.get(s["id"], {}).get("edited")]
            if todo:
                model = self.s.llm_model or "unset"
                lines = [s["src_text"] for s in todo]
                ahead = self._ahead.pop((ctx.job_id, lang), None)
                if ahead and ahead[0] == lines:
                    out = await ahead[1]
                else:
                    if ahead:
                        ahead[1].cancel()
                    out = await translate.translate(self.llm, lines, lang, await self.glossary(), model, ctx.usage)
                out, verdicts = await self.guard_lines(ctx, lang, lines, list(out))
                for s, text, verdict in zip(todo, out, verdicts):
                    fields = {"text": text, **(lineguard.flag_fields(verdict) if verdict is not None else {})}
                    if s["id"] in existing:
                        existing[s["id"]] = await self.store.update("translations", existing[s["id"]]["id"],
                                                                    fields) or existing[s["id"]]
                    else:
                        existing[s["id"]] = await self.store.insert(
                            "translations", {"segment_id": s["id"], "lang": lang, **fields})

        vspec = await self.voice_spec(ctx, lang)
        slot_list = fit.slots([s["start_s"] for s in segs], meta["duration"])
        for i, s in enumerate(segs):
            await self._voice_line(ctx, lang, s, existing[s["id"]], slot_list[i], vspec)
        await self._mix_render(ctx, meta, lang)

    # ---------- v1.2: guards, and a line no voice made ----------
    def _judge(self) -> Any:
        """Who judges a dub line against its source: the injected translator in a test, else `get_judge`."""
        return self._llm if self._llm is not None else get_judge(ENGINE.get() or None, mode=MODE.get())

    async def guard_lines(self, ctx: Ctx, lang: str, src: list[str], out: list[str],
                          retranslate: Any = None) -> tuple[list[str], list[dict[str, Any] | None]]:
        """The script guard and the content-shift check on every translated line of a language, before the voice
        (app/v1/lineguard.py). Returns the lines to dub and a verdict per line (None with both guards off)."""
        script, shift = v1mode.on("script_guard", self.s), v1mode.on("shift_check", self.s)
        if not (script or shift) or not src:
            return out, [None] * len(out)
        glossary = await self.glossary()

        async def again(idx: list[int]) -> list[str]:
            ctx.usage["llm_calls"] = ctx.usage.get("llm_calls", 0) + 1
            return list(await self.llm.translate_batch([src[i] for i in idx], lang, glossary))
        judge = self._judge()
        key = au.cache_key("guard-1", src, out, lang, script, shift, trace.provider_name(judge))
        got = cache.get_json("guard", key)
        if got is None:
            lines, verdicts = await lineguard.check(src, out, lang, judge=judge, retranslate=retranslate or again,
                                                    script=script, shift=shift)
            if not any(v.get("shift") == "not_checked" for v in verdicts):   # an unchecked answer is asked again next time
                cache.put_json("guard", key, {"lines": lines, "verdicts": verdicts})
        else:
            lines, verdicts = got["lines"], got["verdicts"]
        found = lineguard.summary(verdicts)
        ctx.guards[lang] = {**ctx.guards.get(lang, {}), **found}
        if found["script_flagged"] or found["shift_flagged"]:
            self._warn(ctx, f"{found['script_flagged'] + found['shift_flagged']} {lang} lines did not pass a guard "
                            "and are marked for your ear.")
        if shift and found["shift_not_checked"]:
            self._warn(ctx, f"{found['shift_not_checked']} {lang} lines could not be checked against their source "
                            "(the judge did not answer).")
        if v1mode.on("trace", self.s):
            trace.event("studio_guard", job=ctx.job_id, lang=lang, judge=trace.provider_name(judge), **found)
        return lines, list(verdicts)

    async def _shortened_checked(self, ctx: Ctx, lang: str, src: str, text: str) -> dict[str, Any]:
        """A line that was shortened to fit its slot is judged once more against its source: the check before the
        voice saw the longer line. It is not made again (it was shortened for a reason): flagged, or passed."""
        if not v1mode.on("shift_check", self.s):
            return {}
        got = await guards.judge(self._judge(), [(src, text)], lang, lineguard.JUDGE_TIMEOUT_S)
        g = ctx.guards.setdefault(lang, {})
        g["shortened_checked"] = g.get("shortened_checked", 0) + int(got is not None)
        if got is None:
            return {"guard_shortened": "not_checked"}
        why = "says something different from its source" if got[0]["shift"] else \
            "something that matters in its source is missing" if got[0]["lost"] else ""
        if not why:
            return {"guard_shortened": "ok"}
        g["shortened_flagged"] = g.get("shortened_flagged", 0) + 1
        return {"guard_shortened": "flagged", "flagged": True, "flag_reason": f"guard: shortened to fit its slot, and now {why}"}

    async def _unspoken(self, ctx: Ctx, lang: str, seg: dict[str, Any], tr: dict[str, Any], e: Exception) -> dict[str, Any]:
        """No voice made this line. It is never dropped without a trace: the line is marked, the job says so, the
        trace has the event; the video is finished without it."""
        g = ctx.guards.setdefault(lang, {})
        g["unspoken"] = g.get("unspoken", 0) + 1
        self._warn(ctx, f"A {lang} line (line {seg['idx'] + 1}) has no sound: {str(e)[:200]}")
        log.error("job %s %s line %s has NO SOUND: %s", ctx.job_id, lang, seg["idx"], e)
        if v1mode.on("trace", self.s):
            trace.event("studio_unspoken", job=ctx.job_id, lang=lang, idx=seg["idx"],
                        tried=getattr(e, "tried", None) or [{"voice": "?", "error": str(e)[:160]}])
        fields = {"audio_path": None, "unspoken": True, "flagged": True,
                  "flag_reason": f"no voice could say this line ({str(e)[:160]})"}
        return await self.store.update("translations", tr["id"], fields) or {**tr, **fields}

    async def _voice_line(self, ctx: Ctx, lang: str, seg: dict[str, Any], tr: dict[str, Any],
                          slot_s: float, vspec: VoiceSpec) -> dict[str, Any]:
        text = tr["text"]
        chain = v1mode.on("voice_fallback", self.s)
        try:
            async with self._stage(ctx, "voice", lang):
                raw = await voice.synth_line(self.tts, text, lang, vspec, self.s.tts_model, self.s.tts_sample_rate,
                                             ctx.usage, ctx.warnings, fallback=chain)
        except ProviderError as e:
            if not chain:
                raise
            return await self._unspoken(ctx, lang, seg, tr, e)
        async with self._stage(ctx, "fit", lang):
            native = 1.0
            # v1 (`V1_FIT_115`): a line is sped up by at most 1.15x; past that it is shortened.
            max_speed = self.s.v1_fit_max_speed if v1mode.on("fit_115", self.s) else fit.MAX_SPEED
            need = fit.needed_speed(au.duration_s(raw), slot_s)
            if need > 1.05 and getattr(self.tts, "native_speed", False) and self.tts.engine_speaks(lang, vspec):
                # Our GPU voice copies the pace of its sample, and a recorded voice at a natural pace can run far
                # past the slot. It speaks faster by itself with no loss down to about 300 ms a word (measured
                # 2026-11-21), so it is asked again at the speed that fits, within that floor and 1.5x.
                per_word = au.duration_s(raw) * 1000 / max(1, len(text.split()))
                native = min(need, self.s.gpu_voice_pace_max, per_word / 300)
                if native > 1.05:
                    try:
                        raw = await voice.synth_line(self.tts, text, lang, vspec, self.s.tts_model,
                                                     self.s.tts_sample_rate, ctx.usage, ctx.warnings, speed=native,
                                                     fallback=chain)
                    except ProviderError:
                        if not chain:
                            raise
                        native = 1.0     # the faster take could not be made: the first one stays
                else:
                    native = 1.0
            if fit.needed_speed(au.duration_s(raw), slot_s) > max_speed and not tr.get("edited"):
                try:
                    if native > 1.0:
                        # The voice's pace is known now, so the limit is given in words: what fits the slot at
                        # the 1.35x squeeze, less a tenth.
                        fits = int(len(text.split()) * slot_s * max_speed / au.duration_s(raw) * 0.9)
                        shorter = await self.llm.shorten(text, lang, slot_s * 1.25, max_words=max(3, fits))
                    else:
                        shorter = await self.llm.shorten(text, lang, slot_s * 1.25)
                    if shorter and len(shorter) < len(text):
                        shorter_raw = await voice.synth_line(self.tts, shorter, lang, vspec, self.s.tts_model,
                                                             self.s.tts_sample_rate, ctx.usage, ctx.warnings,
                                                             speed=native, fallback=chain)
                        text, raw = shorter, shorter_raw
                except ProviderError as e:
                    self._warn(ctx, f"Could not shorten a {lang} line; sped up to 1.35x ({e})"[:200])
            lines_dir = ctx.dir / "lines"
            lines_dir.mkdir(exist_ok=True)
            out = lines_dir / f"{lang}_{seg['idx']:03}.wav"
            speed = await asyncio.to_thread(fit.fit_clip, raw, slot_s, out, max_speed)
        if v1mode.on("trace", self.s):
            on_gpu = bool(getattr(self.tts, "native_speed", False) and self.tts.engine_speaks(lang, vspec))
            trace.studio_line(ctx.job_id, lang, seg["idx"], mode="studio", engine=ENGINE.get() or "cloud",
                              words=len(text.split()), slot_s=round(slot_s, 3), dur_s=round(au.duration_s(out), 3),
                              speed=speed, native_speed=round(native, 2), tts="gpu_voice" if on_gpu else "hosted",
                              clone=vspec["kind"] == "clone", edited=bool(tr.get("edited")),
                              gpu_s=round(float(getattr(getattr(self.tts, "gpu", None), "last_synth_ms", 0) or 0) / 1000, 3)
                              if on_gpu and not ctx.usage.get("tts_cache_hits") else None)
        fields: dict[str, Any] = {"text": text, "audio_path": str(out.relative_to(ctx.dir)), "fit_speed": speed}
        if chain and tr.get("unspoken"):
            fields["unspoken"] = False
        if text != tr["text"] and not tr.get("edited"):
            fields |= await self._shortened_checked(ctx, lang, seg.get("src_text") or "", text)
        return await self.store.update("translations", tr["id"], fields) or {**tr, **fields}

    async def _mix_render(self, ctx: Ctx, meta: dict[str, Any], lang: str) -> None:
        segs = await self.spoken_segments(ctx.job_id)
        trs = {t["segment_id"]: t for t in await self.store.select_in(
            "translations", "segment_id", [s["id"] for s in segs], lang=lang)}
        lines = [(s["start_s"], ctx.dir / trs[s["id"]]["audio_path"]) for s in segs
                 if s["id"] in trs and trs[s["id"]].get("audio_path")]
        out_dir = ctx.dir / "out"
        out_dir.mkdir(exist_ok=True)
        mix_wav = ctx.dir / f"mix_{lang}.wav"
        async with self._stage(ctx, "mix", lang):
            bg = Path(meta["background"]) if meta.get("background") else None
            if hq.is_hq(meta, self.s):
                # v1: the background follows the voice's own loudness, and the mix is brought to one loudness.
                from app.v1.hq import finish
                await asyncio.to_thread(finish.mix, lines, bg, meta["duration"], mix_wav, duck_db=self.s.v1_hq_duck_db)
                await asyncio.to_thread(finish.loudness, mix_wav, self.s.v1_hq_loudness_lufs)
            else:
                await asyncio.to_thread(mix.mix, lines, bg, meta["duration"], mix_wav)
        async with self._stage(ctx, "render", lang):
            mp4 = out_dir / f"{meta['name']}_{lang}.mp4"
            srt = out_dir / f"{meta['name']}_{lang}.srt"
            cues = [(s["start_s"], s["end_s"], trs[s["id"]]["text"]) for s in segs if s["id"] in trs]
            await asyncio.to_thread(render.render, ctx.dir / meta["source"], mix_wav, mp4, srt, cues)
            mp4_key, srt_key = await publish_output(ctx.job_id, mp4), await publish_output(ctx.job_id, srt)
            await self.store.delete("renders", job_id=ctx.job_id, lang=lang)
            await self.store.insert("renders", {"job_id": ctx.job_id, "lang": lang,
                                                "mp4_path": mp4_key, "srt_path": srt_key})
        events.publish(ctx.job_id, {"type": "render", "lang": lang})

    # ---------- edits + re-render ----------
    async def edit_line(self, job_id: str, translation_id: str, text: str) -> dict[str, Any]:
        """Re-run stages 7-10 for one line, then re-mix and re-render that language."""
        ctx = Ctx(job_id, self.job_dir(job_id))
        self._use_engine(ctx.dir)
        tr = await self.store.get("translations", translation_id)
        if not tr:
            raise KeyError("translation not found")
        seg = await self.store.get("segments", tr["segment_id"])
        if not seg or seg["job_id"] != job_id:
            raise KeyError("translation not in this job")
        async with self._locks[job_id]:
            meta = self._meta(ctx.dir)
            tr = await self.store.update("translations", translation_id, {"text": text.strip(), "edited": True}) \
                or tr
            segs = await self.spoken_segments(job_id)
            slot_list = fit.slots([s["start_s"] for s in segs], meta["duration"])
            slot = next(sl for s, sl in zip(segs, slot_list) if s["id"] == seg["id"])
            events.publish(job_id, {"type": "line", "status": "running", "translation_id": translation_id})
            tr = await self._voice_line(ctx, tr["lang"], seg, tr, slot, await self.voice_spec(ctx, tr["lang"]))
            await self._mix_render(ctx, meta, tr["lang"])
        await self._save_stats(ctx, merge=True)
        events.publish(job_id, {"type": "line", "status": "done", "translation_id": translation_id})
        return tr

    async def pick_version(self, job_id: str, translation_id: str, alt: int) -> dict[str, Any]:
        """v1 HQ: use another version of a line that was already made (the editor's one-click swap)."""
        ctx = Ctx(job_id, self.job_dir(job_id))
        self._use_engine(ctx.dir)
        tr = await self.store.get("translations", translation_id)
        seg = await self.store.get("segments", tr["segment_id"]) if tr else None
        if not tr or not seg or seg["job_id"] != job_id:
            raise KeyError("translation not in this job")
        async with self._locks[job_id]:
            row = await hq.pick_alt(self, ctx, self._meta(ctx.dir), tr, seg, alt)
        await self._save_stats(ctx, merge=True)
        events.publish(job_id, {"type": "line", "status": "done", "translation_id": translation_id})
        return row

    async def run_hq_batch(self, job_ids: list[str]) -> dict[str, str]:
        """v1 HQ: several jobs phase by phase (audio for all, then text for all, then voice for all), so a model
        that is loaded for one phase serves every job. Returns job id -> done | failed."""
        state: dict[str, dict[str, Any]] = {}
        for jid in job_ids:
            job = await self.store.get("jobs", jid)
            d = self.job_dir(jid)
            if not job or not (d / "meta.json").exists() or not hq.is_hq(self._meta(d), self.s):
                continue
            ctx = Ctx(jid, d)
            ctx.timer.timings["ingest"] = 0.0
            state[jid] = {"ctx": ctx, "meta": self._meta(d), "job": job, "ok": True}
            await self._set(ctx, status="running")
        for phase in ("a", "b", "c"):
            for jid, st in state.items():
                if not st["ok"]:
                    continue
                ctx, meta, job = st["ctx"], st["meta"], st["job"]
                self._use_engine(ctx.dir)
                MODE.set("studio_hq")
                stages = st.setdefault("stages", hq.stages_for(jid, ENGINE.get()))
                try:
                    async with self._locks[jid]:
                        if phase == "a":
                            await hq.phase_a(self, ctx, meta, stages)
                        elif phase == "b":
                            await hq.phase_b(self, ctx, meta, stages, job["target_langs"])
                        else:
                            for lang in job["target_langs"]:
                                await hq.phase_c(self, ctx, meta, stages, lang)
                            hq.note_fallbacks(self, ctx, stages)
                except Exception as e:  # noqa: BLE001 - one job's failure does not stop the others
                    log.exception("hq batch: job %s failed in phase %s", jid, phase)
                    st["ok"] = False
                    await self._set(ctx, status="failed", error=_user_error(e))
        out: dict[str, str] = {}
        for jid, st in state.items():
            ctx = st["ctx"]
            if st["ok"]:
                await self._set(ctx, status="done", stage=None)
            await self._save_stats(ctx)
            events.publish(jid, {"type": "end", "job": await self.store.get("jobs", jid)})
            out[jid] = "done" if st["ok"] else "failed"
        return out

    async def render_langs(self, job_id: str, langs: list[str]) -> None:
        """Render (or add) languages for a finished job; STT is never re-run."""
        ctx = Ctx(job_id, self.job_dir(job_id))
        self._use_engine(ctx.dir)
        job = await self.store.get("jobs", job_id)
        if not job:
            return
        new = [lg for lg in langs if lg not in job["target_langs"]]
        if new:
            await self.store.update("jobs", job_id, {"target_langs": job["target_langs"] + new})
        await self._set(ctx, status="running")
        try:
            async with self._locks[job_id]:
                meta = self._meta(ctx.dir)
                if hq.is_hq(meta, self.s):
                    MODE.set("studio_hq")
                    await hq.add_langs(self, ctx, meta, langs, ENGINE.get())
                else:
                    await self._pretranslate(ctx, langs)
                    for lang in langs:
                        await self._process_lang(ctx, meta, lang)
            await self._set(ctx, status="done", stage=None)
        except Exception as e:  # noqa: BLE001
            log.exception("render %s failed", job_id)
            await self._set(ctx, status="failed", error=_user_error(e))
        finally:
            self._drop_ahead(job_id)
            await self._save_stats(ctx, merge=True)
            events.publish(job_id, {"type": "end", "job": await self.store.get("jobs", job_id)})

    def start_render(self, job_id: str, langs: list[str]) -> None:
        task = asyncio.create_task(self.render_langs(job_id, langs))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # ---------- helpers ----------
    async def spoken_segments(self, job_id: str) -> list[dict[str, Any]]:
        segs = await self.store.select("segments", order="idx", job_id=job_id)
        return [s for s in segs if (s.get("src_text") or "").strip()]

    async def glossary(self) -> list[str]:
        terms = [t["term"] for t in await self.store.select("glossary_terms")]
        return list(dict.fromkeys(DEFAULT_GLOSSARY + terms))

    async def voice_spec(self, ctx: Ctx, lang: str) -> VoiceSpec:
        """Cloned voice only for a profile with recorded consent (golden rule 4); else stock for `lang`."""
        job = await self.store.get("jobs", ctx.job_id) or {}
        pid = job.get("voice_profile_id")
        if pid:
            p = await self.store.get("voice_profiles", pid)
            if p and p.get("consent_at") and p.get("embedding") and not p.get("deleted_at"):
                emb = p["embedding"]
                if ENGINE.get() == "gpu" and p.get("ref_path") and p.get("ref_text") and not emb.get("ref_path"):
                    # A streamer's recorded voice: our engine speaks it from the stored sample.
                    emb = {**emb, "ref_path": p["ref_path"], "ref_text": p["ref_text"], "consent_at": p["consent_at"]}
                return {"kind": "clone", "embedding": emb}
            self._warn(ctx, "Voice profile has no consent or was deleted; using a stock voice.")
        return voice.stock_voice(lang)

    async def _set(self, ctx: Ctx, **fields: Any) -> None:
        await self.store.update("jobs", ctx.job_id, fields)
        events.publish(ctx.job_id, {"type": "status", **fields})

    def _warn(self, ctx: Ctx, msg: str) -> None:
        if msg not in ctx.warnings:
            ctx.warnings.append(msg)
            events.publish(ctx.job_id, {"type": "warning", "message": msg})

    def _stage(self, ctx: Ctx, name: str, lang: str | None = None) -> "_StageScope":
        return _StageScope(self, ctx, name, lang)

    async def _save_stats(self, ctx: Ctx, merge: bool = False) -> None:
        job = await self.store.get("jobs", ctx.job_id) or {}
        old = job.get("stage_timings") or {}
        timings = dict(old) if merge else {}
        for k, v in ctx.timer.timings.items():
            timings[k] = round((timings.get(k, 0.0) if merge else 0.0) + v, 3)
        timings["_total"] = round(sum(v for k, v in timings.items()
                                      if not k.startswith("_") and ":" not in k), 3)
        usage = dict(old.get("_usage") or {}) if merge else {}
        for k, v in ctx.usage.items():
            usage[k] = round(usage.get(k, 0) + v, 2)
        timings["_usage"] = usage
        warnings = (list(old.get("_warnings") or []) if merge else []) + ctx.warnings
        timings["_warnings"] = list(dict.fromkeys(warnings))[-20:]
        if ctx.guards or (merge and old.get("_guards")):
            timings["_guards"] = {**(old.get("_guards") or {} if merge else {}), **ctx.guards}
        timings["_updated_at"] = now_iso()
        await self.store.update("jobs", ctx.job_id, {"stage_timings": timings})

    @staticmethod
    def _meta(d: Path) -> dict[str, Any]:
        return json.loads((d / "meta.json").read_text(encoding="utf-8"))

    @staticmethod
    def _write_meta(d: Path, meta: dict[str, Any]) -> None:
        (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


class _StageScope:
    """Times a stage, updates job.stage and emits start/done events."""

    def __init__(self, runner: StudioRunner, ctx: Ctx, name: str, lang: str | None) -> None:
        self.r, self.ctx, self.name, self.lang = runner, ctx, name, lang
        self._cm = ctx.timer.stage(name)

    async def __aenter__(self) -> None:
        self._t0 = asyncio.get_running_loop().time()
        self._cm.__enter__()
        if self.name not in ("voice", "fit"):  # per-line stages are too chatty to persist each time
            await self.r.store.update("jobs", self.ctx.job_id, {"stage": self.name})
        events.publish(self.ctx.job_id, {"type": "stage", "stage": self.name, "lang": self.lang,
                                         "status": "running"})

    async def __aexit__(self, *exc: Any) -> None:
        self._cm.__exit__(*exc)
        secs = round(asyncio.get_running_loop().time() - self._t0, 3)
        if self.lang:
            k = f"{self.name}:{self.lang}"
            self.ctx.timer.timings[k] = round(self.ctx.timer.timings.get(k, 0.0) + secs, 3)
        events.publish(self.ctx.job_id, {"type": "stage", "stage": self.name, "lang": self.lang,
                                         "status": "failed" if exc[0] else "done", "seconds": secs})


class PipelineError(RuntimeError):
    pass


def _user_error(e: Exception) -> str:
    if isinstance(e, (PipelineError, extract.IngestError, ProviderError)):
        return str(e)[:500]
    return f"{type(e).__name__}: {str(e)[:400]}"


runner = StudioRunner()
