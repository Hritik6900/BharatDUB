"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Captions, Check, Clapperboard, Download, LoaderCircle, Play, Plus, X } from "lucide-react";
import { Shell } from "@/components/layout/Shell";
import { ABPlayer, type Track } from "@/components/player/ABPlayer";
import { Button, LinkButton } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { VoiceOrb } from "@/components/voice/VoiceOrb";
import { API_BASE, api, fmtSeconds, type Job, type Output, type Segment } from "@/lib/api";
import { STUDIO_LANGS as TARGET_LANGS, lang } from "@/lib/langs";

const STAGES: [string, string][] = [
  ["extract", "Extract audio"],
  ["separate", "Separate voice and music"],
  ["segment", "Find speech"],
  ["transcribe", "Transcribe"],
  ["translate", "Translate"],
  ["voice", "Speak each line"],
  ["fit", "Fit lines to timing"],
  ["mix", "Mix over background"],
  ["render", "Render video and subtitles"],
];
type StageState = "waiting" | "running" | "done" | "failed";

export default function JobPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const [job, setJob] = useState<Job | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [state, setState] = useState<Record<string, StageState>>({});
  const [activeLang, setActiveLang] = useState<string | null>(null);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [outputs, setOutputs] = useState<Output[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [track, setTrack] = useState<string>("");
  const [version, setVersion] = useState(0);
  const [seek, setSeek] = useState<{ t: number; n: number } | null>(null);

  const refresh = useCallback(async () => {
    try {
      const j = await api<Job>(`/api/jobs/${jobId}`);
      setJob(j);
      if (j.status === "done" || j.status === "failed") {
        setSegments(await api<Segment[]>(`/api/jobs/${jobId}/segments`));
        setOutputs(await api<Output[]>(`/api/jobs/${jobId}/outputs`));
      }
    } catch {
      setNotFound(true);
    }
  }, [jobId]);

  useEffect(() => {
    refresh();
    const es = new EventSource(`${API_BASE}/api/jobs/${jobId}/events`);
    es.addEventListener("snapshot", (e) => setJob(JSON.parse((e as MessageEvent).data)));
    es.addEventListener("stage", (e) => {
      const ev = JSON.parse((e as MessageEvent).data);
      setState((s) => ({ ...s, [ev.stage]: ev.status === "running" ? "running" : ev.status === "failed" ? "failed" : "done" }));
      if (ev.lang) setActiveLang(ev.lang);
    });
    es.addEventListener("warning", (e) => setWarnings((w) => [...new Set([...w, JSON.parse((e as MessageEvent).data).message])]));
    es.addEventListener("render", () => refresh());
    es.addEventListener("status", () => refresh());
    es.addEventListener("end", () => {
      refresh();
      es.close();
    });
    es.onerror = () => {}; // EventSource retries on its own
    return () => es.close();
  }, [jobId, refresh]);

  const timings = job?.stage_timings ?? {};
  const allWarnings = [...new Set([...(timings._warnings ?? []), ...warnings])];
  const stageStatus = (k: string): StageState => {
    if (state[k]) return state[k];
    if (job?.status === "done") return "done";
    if (job?.stage === k) return job.status === "failed" ? "failed" : "running";
    return typeof timings[k] === "number" ? "done" : "waiting";
  };

  const tracks: Track[] = useMemo(() => {
    const t: Track[] = [{ key: "src", label: "Original", url: `${API_BASE}/api/jobs/${jobId}/source` }];
    for (const o of outputs) t.push({ key: o.lang, label: lang(o.lang).name, url: `${o.mp4_url}${o.mp4_url.includes("?") ? "&" : "?"}v=${version}` });
    return t;
  }, [outputs, jobId, version]);
  useEffect(() => {
    if (!track && outputs.length) setTrack(outputs[0].lang);
  }, [outputs, track]);

  if (notFound)
    return (
      <Shell>
        <div className="mx-auto max-w-3xl px-5 py-24 text-center sm:px-8">
          <h1 className="h-display text-5xl">Video not found</h1>
          <p className="mt-4 text-muted">It may have expired; uploads are deleted after 24 hours.</p>
          <LinkButton href="/studio" className="mt-8">Dub a new video</LinkButton>
        </div>
      </Shell>
    );

  const done = job?.status === "done";
  const failed = job?.status === "failed";
  const reviewLang = track && track !== "src" ? track : outputs[0]?.lang;
  const doneCount = STAGES.filter(([k]) => stageStatus(k) === "done").length;
  return (
    <Shell>
      <div className="mx-auto max-w-6xl px-5 pb-24 pt-10 sm:px-8 sm:pt-14">
        <header className="rise">
          <Link href="/studio" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
            <ArrowLeft aria-hidden className="size-4" />
            Studio
          </Link>
          <p className="eyebrow mt-6 flex items-center gap-2">
            <Clapperboard aria-hidden className="size-3.5" />
            <span className="max-w-[60vw] truncate normal-case tracking-normal">{job?.source_path ?? "…"}</span>
          </p>
          <h1 className="h-display mt-4 text-[clamp(2.4rem,5.5vw,4rem)]">
            {done ? <>Your dub is <em>ready</em></> : failed ? "Dubbing stopped" : <>Dubbing your <em>video</em></>}
          </h1>
          {job && (
            <ul className="mt-5 flex flex-wrap gap-2 text-sm">
              <li className="rounded-chip border border-line bg-surface px-3 py-1.5"><span className="tnum">{fmtSeconds(job.duration_s)}</span> video</li>
              {job.target_langs.map((c) => (
                <li key={c} className="inline-flex items-center gap-2 rounded-chip border border-line bg-surface px-3 py-1.5">
                  <span className="size-2 rounded-full" style={{ background: lang(c).hue }} />
                  {lang(c).name}
                </li>
              ))}
              {typeof timings._total === "number" && done && (
                <li className="rounded-chip border border-line bg-surface px-3 py-1.5">finished in <span className="tnum font-semibold">{fmtSeconds(timings._total)}</span></li>
              )}
            </ul>
          )}
        </header>

        <div className={`mt-10 grid grid-cols-1 gap-8 ${done ? "lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]" : "lg:grid-cols-2"}`}>
          <div className={done ? "" : "order-2 lg:order-1"}>
            {done && tracks.length > 1 ? (
              <ABPlayer tracks={tracks} active={track || tracks[1].key} onActive={setTrack} segments={segments} seekTo={seek} />
            ) : failed ? (
              <Notice tone="error" role="alert">
                <span className="block font-medium">What went wrong</span>
                {job?.error}
              </Notice>
            ) : (
              <div className="card grid aspect-video place-items-center overflow-hidden p-8 text-center">
                <div className="flex flex-col items-center">
                  <VoiceOrb size={132} />
                  <p className="mt-8 text-lg font-medium">Working on it</p>
                  <p className="mt-1 max-w-[34ch] text-sm text-muted">The player appears here when the first language is ready. You can leave this page open.</p>
                </div>
              </div>
            )}
          </div>

          <section aria-labelledby="stages-h" className={`card p-5 sm:p-6 ${done ? "" : "order-1 lg:order-2"}`}>
            <div className="flex items-center justify-between">
              <h2 id="stages-h" className="eyebrow">Steps</h2>
              <span className="tnum font-mono text-xs text-muted">{doneCount} / {STAGES.length}</span>
            </div>
            <div className="mt-3 h-1 overflow-hidden rounded-chip bg-line" aria-hidden>
              <div className="spectrum h-full rounded-chip transition-[width] duration-700" style={{ width: `${(doneCount / STAGES.length) * 100}%` }} />
            </div>
            <ol className="mt-4">
              {STAGES.map(([k, label]) => {
                const st = stageStatus(k);
                const secs = typeof timings[k] === "number" ? (timings[k] as number) : null;
                return (
                  <li key={k} className="flex items-center gap-3.5 py-2" aria-current={st === "running" ? "step" : undefined}>
                    <span
                      className={`grid size-7 shrink-0 place-items-center rounded-full border ${
                        st === "done" ? "border-fg bg-fg text-on-fg" : st === "failed" ? "border-danger text-danger" : st === "running" ? "border-fg" : "border-line text-muted"
                      }`}
                    >
                      {st === "done" ? <Check aria-hidden className="size-3.5" /> : st === "failed" ? <X aria-hidden className="size-3.5" /> : st === "running" ? <LoaderCircle aria-hidden className="size-3.5 animate-spin" /> : <span className="size-1.5 rounded-full bg-line" />}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className={st === "waiting" ? "text-muted" : st === "running" ? "font-medium" : ""}>{label}</span>
                      {st === "running" && activeLang && ["translate", "voice", "fit", "mix", "render"].includes(k) && <span className="text-sm text-muted"> · {lang(activeLang).name}</span>}
                      {st === "running" && (
                        <span className="mt-1.5 block h-1 overflow-hidden rounded-chip bg-line">
                          <span className="block h-full w-1/3 animate-[slide_1.2s_ease-in-out_infinite] rounded-chip bg-fg" />
                        </span>
                      )}
                    </span>
                    <span className="tnum shrink-0 font-mono text-xs text-muted">{secs != null ? fmtSeconds(secs) : st === "failed" ? "failed" : ""}</span>
                  </li>
                );
              })}
            </ol>
            {allWarnings.length > 0 && (
              <ul className="mt-4 space-y-2">
                {allWarnings.map((w) => <li key={w}><Notice tone="warn">{w}</Notice></li>)}
              </ul>
            )}
            {done && outputs.length > 0 && (
              <div className="mt-6 border-t border-line pt-6">
                <h2 className="eyebrow">Downloads</h2>
                <ul className="mt-4 space-y-2.5">
                  {outputs.map((o) => (
                    <li key={o.lang} className="flex flex-wrap items-center gap-2">
                      <a className="inline-flex h-10 flex-1 items-center gap-2.5 rounded-chip border border-line bg-surface px-4 text-[0.95rem] transition-colors hover:border-fg" href={o.mp4_url} download>
                        <span className="size-2 rounded-full" style={{ background: lang(o.lang).hue }} />
                        {lang(o.lang).name} video
                        <Download aria-hidden className="ml-auto size-4" />
                      </a>
                      <a aria-label={`${lang(o.lang).name} subtitles`} className="inline-flex h-10 items-center gap-2 rounded-chip border border-line bg-surface px-4 text-[0.95rem] transition-colors hover:border-fg" href={o.srt_url} download>
                        <Captions aria-hidden className="size-4" />
                        SRT
                      </a>
                    </li>
                  ))}
                </ul>
                <AddLanguage jobId={jobId} have={job?.target_langs ?? []} onStarted={refresh} />
              </div>
            )}
          </section>
        </div>

        {done && reviewLang && (
          <Review
            jobId={jobId}
            lang={reviewLang}
            segments={segments}
            onPlay={(t) => setSeek({ t, n: Date.now() })}
            onUpdated={async () => {
              setSegments(await api<Segment[]>(`/api/jobs/${jobId}/segments`));
              setVersion((v) => v + 1);
            }}
          />
        )}
      </div>
    </Shell>
  );
}

function AddLanguage({ jobId, have, onStarted }: { jobId: string; have: string[]; onStarted: () => void }) {
  const missing = TARGET_LANGS.filter((l) => !have.includes(l.code));
  const [msg, setMsg] = useState("");
  if (!missing.length) return null;
  return (
    <div className="mt-6">
      <p className="text-sm text-muted">Add a language. Your transcript is reused, no new upload.</p>
      <div className="mt-2.5 flex flex-wrap gap-2">
        {missing.map((l) => (
          <button
            key={l.code}
            onClick={async () => {
              try {
                await api(`/api/jobs/${jobId}/render`, { method: "POST", body: JSON.stringify({ langs: [l.code] }) });
                setMsg(`Adding ${l.name}…`);
                onStarted();
                setTimeout(() => location.reload(), 600);
              } catch (e) {
                setMsg((e as Error).message);
              }
            }}
            className="inline-flex h-9 items-center gap-2 rounded-chip border border-dashed border-line px-3 text-sm transition-colors hover:border-fg"
          >
            <Plus aria-hidden className="size-3.5" />
            <span className="size-2 rounded-full" style={{ background: l.hue }} />
            {l.name}
          </button>
        ))}
      </div>
      {msg && <p className="mt-2 text-sm" role="status">{msg}</p>}
    </div>
  );
}

function Review({ jobId, lang: code, segments, onPlay, onUpdated }: { jobId: string; lang: string; segments: Segment[]; onPlay: (t: number) => void; onUpdated: () => void }) {
  const l = lang(code);
  const rows = segments.filter((s) => s.src_text.trim());
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<Record<string, string>>({});
  const [toast, setToast] = useState("");

  const save = async (tid: string) => {
    setStatus((s) => ({ ...s, [tid]: "Re-rendering this line…" }));
    try {
      await api(`/api/jobs/${jobId}/translations/${tid}`, { method: "PATCH", body: JSON.stringify({ text: draft[tid] }) });
      setStatus((s) => ({ ...s, [tid]: "Updated" }));
      setDraft((d) => {
        const n = { ...d };
        delete n[tid];
        return n;
      });
      setToast("Updated");
      setTimeout(() => setToast(""), 2500);
      onUpdated();
    } catch (e) {
      setStatus((s) => ({ ...s, [tid]: `Failed: ${(e as Error).message}` }));
    }
  };

  return (
    <section aria-labelledby="review-h" className="mt-20">
      <p className="eyebrow">Review</p>
      <h2 id="review-h" className="h-display mt-3 text-[clamp(2rem,4vw,3rem)]">
        The {l.name} <em>lines</em>
      </h2>
      <p className="mt-3 max-w-[58ch] text-muted">Edit a line and save. Only that line is re-voiced, then the video is re-rendered.</p>
      <div className="card relative mt-8 overflow-x-auto" data-lenis-prevent>
        <table className="w-full min-w-[720px] text-left">
          <thead className="border-b border-line">
            <tr className="eyebrow">
              <th className="w-20 px-5 py-4 font-normal">Time</th>
              <th className="px-4 py-4 font-normal">Original</th>
              <th className="px-4 py-4 font-normal">
                <span className="inline-flex items-center gap-2">
                  <span className="size-2 rounded-full" style={{ background: l.hue }} />
                  {l.name}
                </span>
              </th>
              <th className="w-32 px-4 py-4 font-normal"><span className="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map((s) => {
              const tr = s.translations.find((t) => t.lang === code);
              if (!tr) return null;
              const val = draft[tr.id] ?? tr.text;
              const dirty = draft[tr.id] != null && draft[tr.id] !== tr.text;
              return (
                <tr key={s.id} className="align-top">
                  <td className="tnum px-5 py-4 font-mono text-xs text-muted">{s.start_s.toFixed(1)} s</td>
                  <td className="px-4 py-4 text-muted" lang="hi">{s.src_text}</td>
                  <td className="px-3 py-2.5">
                    <textarea
                      lang={l.short}
                      aria-label={`${l.name} line at ${s.start_s.toFixed(1)} seconds`}
                      value={val}
                      onChange={(e) => setDraft((d) => ({ ...d, [tr.id]: e.target.value }))}
                      rows={Math.max(1, Math.ceil(val.length / 48))}
                      className="w-full resize-y rounded-[10px] border border-transparent bg-transparent p-1.5 transition-colors hover:border-line focus:border-fg focus:outline-none"
                    />
                    <span className="block px-1.5 text-xs text-muted" role="status">
                      {status[tr.id] ?? (tr.edited ? "Edited" : "")}
                      {tr.fit_speed && tr.fit_speed > 1.01 ? `${status[tr.id] || tr.edited ? " · " : ""}sped up ${tr.fit_speed.toFixed(2)}x to fit` : ""}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2">
                      <button aria-label={`Play from ${s.start_s.toFixed(1)} s`} onClick={() => onPlay(s.start_s)} className="grid size-9 place-items-center rounded-chip border border-line transition-colors hover:border-fg">
                        <Play aria-hidden className="size-3.5 translate-x-px fill-current" />
                      </button>
                      {dirty && <Button size="sm" onClick={() => save(tr.id)}>Save</Button>}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {toast && (
        <div role="status" className="rise fixed bottom-6 left-1/2 z-50 inline-flex -translate-x-1/2 items-center gap-2 rounded-chip bg-fg px-5 py-2.5 text-on-fg shadow-card">
          <Check aria-hidden className="size-4" />
          {toast}
        </div>
      )}
    </section>
  );
}
