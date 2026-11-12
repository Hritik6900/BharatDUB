"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Nav } from "@/components/layout/Nav";
import { ABPlayer, type Track } from "@/components/player/ABPlayer";
import { Button } from "@/components/ui/Button";
import { API_BASE, api, fmtSeconds, type Job, type Output, type Segment } from "@/lib/api";
import { TARGET_LANGS, lang } from "@/lib/langs";

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
      <>
        <Nav />
        <main className="mx-auto max-w-3xl px-4 py-16 sm:px-8">
          <h1 className="font-display text-3xl font-semibold">Video not found</h1>
          <p className="mt-3 text-slate">It may have expired; uploads are deleted after 24 hours.</p>
          <Link href="/studio" className="mt-6 inline-block underline">Dub a new video</Link>
        </main>
      </>
    );

  const done = job?.status === "done";
  const reviewLang = track && track !== "src" ? track : outputs[0]?.lang;
  return (
    <>
      <Nav />
      <main className="mx-auto max-w-6xl px-4 py-10 sm:px-8 sm:py-14">
        <p className="text-sm text-slate"><Link href="/studio" className="hover:text-fg">Studio</Link> / {job?.source_path ?? "…"}</p>
        <h1 className="mt-2 font-display text-[clamp(1.8rem,4vw,2.6rem)] font-semibold leading-tight">
          {done ? "Your dub is ready" : job?.status === "failed" ? "Dubbing stopped" : "Dubbing your video"}
        </h1>
        {job && (
          <p className="mt-2 text-slate">
            {fmtSeconds(job.duration_s)} video ·{" "}
            {job.target_langs.map((c) => lang(c).name).join(", ")}
            {typeof timings._total === "number" && done && <> · finished in <span className="tnum">{fmtSeconds(timings._total)}</span></>}
          </p>
        )}

        <div className={`mt-10 grid gap-10 ${done ? "lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]" : "lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]"}`}>
          <div className={done ? "" : "order-2 lg:order-1"}>
            {done && tracks.length > 1 ? (
              <ABPlayer tracks={tracks} active={track || tracks[1].key} onActive={setTrack} segments={segments} seekTo={seek} />
            ) : job?.status === "failed" ? (
              <div role="alert" className="rounded-panel border border-[var(--bn)] p-5">
                <p className="font-display font-semibold">What went wrong</p>
                <p className="mt-1 text-slate">{job.error}</p>
              </div>
            ) : (
              <div className="grid aspect-video place-items-center rounded-media border border-mist bg-surface text-slate">
                <p>The player appears here when the first language is ready.</p>
              </div>
            )}
          </div>

          <section aria-labelledby="stages-h" className={done ? "" : "order-1 lg:order-2"}>
            <h2 id="stages-h" className="font-display text-lg font-semibold">Steps</h2>
            <ol className="mt-4 space-y-1">
              {STAGES.map(([k, label], i) => {
                const st = stageStatus(k);
                const secs = typeof timings[k] === "number" ? (timings[k] as number) : null;
                return (
                  <li key={k} className="flex items-center gap-4 rounded-panel px-3 py-2.5" aria-current={st === "running" ? "step" : undefined}>
                    <span className={`tnum grid size-7 shrink-0 place-items-center rounded-full border text-sm ${st === "done" ? "border-fg bg-fg text-on-fg" : st === "failed" ? "border-[var(--bn)] text-[var(--bn)]" : "border-mist text-slate"}`}>
                      {st === "done" ? "✓" : i + 1}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className={st === "waiting" ? "text-slate" : ""}>{label}</span>
                      {st === "running" && (
                        <span className="mt-1.5 block h-1 overflow-hidden rounded-chip bg-mist">
                          <span className="block h-full w-1/3 animate-[slide_1.2s_ease-in-out_infinite] rounded-chip bg-[var(--hi)]" />
                        </span>
                      )}
                      {st === "running" && activeLang && ["translate", "voice", "fit", "mix", "render"].includes(k) && (
                        <span className="text-sm text-slate"> · {lang(activeLang).name}</span>
                      )}
                    </span>
                    <span className="tnum shrink-0 text-sm text-slate">{secs != null ? fmtSeconds(secs) : st === "failed" ? "failed" : ""}</span>
                  </li>
                );
              })}
            </ol>
            {allWarnings.length > 0 && (
              <ul className="mt-5 space-y-2 text-sm">
                {allWarnings.map((w) => <li key={w} className="rounded-panel border border-[var(--hi)] px-3 py-2">{w}</li>)}
              </ul>
            )}
            {done && outputs.length > 0 && (
              <div className="mt-8">
                <h2 className="font-display text-lg font-semibold">Downloads</h2>
                <ul className="mt-3 space-y-2">
                  {outputs.map((o) => (
                    <li key={o.lang} className="flex flex-wrap gap-2">
                      <a className="inline-flex h-10 items-center gap-2 rounded-chip border border-mist bg-surface px-4 hover:border-fg" href={o.mp4_url} download>
                        <span className="size-2 rounded-full" style={{ background: lang(o.lang).hue }} />
                        Download {lang(o.lang).name} video
                      </a>
                      <a className="inline-flex h-10 items-center rounded-chip border border-mist bg-surface px-4 hover:border-fg" href={o.srt_url} download>
                        {lang(o.lang).name} subtitles
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
      </main>
      <style>{`@keyframes slide{0%{transform:translateX(-100%)}100%{transform:translateX(300%)}}`}</style>
    </>
  );
}

function AddLanguage({ jobId, have, onStarted }: { jobId: string; have: string[]; onStarted: () => void }) {
  const missing = TARGET_LANGS.filter((l) => !have.includes(l.code));
  const [msg, setMsg] = useState("");
  if (!missing.length) return null;
  return (
    <div className="mt-6">
      <p className="text-sm text-slate">Add a language (your transcript is reused, no new upload):</p>
      <div className="mt-2 flex flex-wrap gap-2">
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
            className="inline-flex h-9 items-center gap-2 rounded-chip border border-mist bg-surface px-3 text-sm hover:border-fg"
          >
            <span className="size-2 rounded-full" style={{ background: l.hue }} /> {l.name}
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
    <section aria-labelledby="review-h" className="mt-16">
      <h2 id="review-h" className="font-display text-2xl font-semibold">Review the {l.name} lines</h2>
      <p className="mt-1 text-slate">Edit a line and save: only that line is re-voiced, then the video is re-rendered.</p>
      <div className="mt-6 overflow-x-auto rounded-panel border border-mist">
        <table className="w-full min-w-[720px] text-left">
          <thead className="border-b border-mist text-sm text-slate">
            <tr>
              <th className="w-20 px-4 py-3 font-normal">Time</th>
              <th className="px-4 py-3 font-normal">Original</th>
              <th className="px-4 py-3 font-normal">{l.name}</th>
              <th className="w-28 px-4 py-3 font-normal"><span className="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-mist">
            {rows.map((s) => {
              const tr = s.translations.find((t) => t.lang === code);
              if (!tr) return null;
              const val = draft[tr.id] ?? tr.text;
              const dirty = draft[tr.id] != null && draft[tr.id] !== tr.text;
              return (
                <tr key={s.id} className="align-top">
                  <td className="tnum px-4 py-3 text-sm text-slate">{s.start_s.toFixed(1)} s</td>
                  <td className="px-4 py-3" lang="hi">{s.src_text}</td>
                  <td className="px-4 py-3">
                    <textarea
                      lang={l.short}
                      aria-label={`${l.name} line at ${s.start_s.toFixed(1)} seconds`}
                      value={val}
                      onChange={(e) => setDraft((d) => ({ ...d, [tr.id]: e.target.value }))}
                      rows={Math.max(1, Math.ceil(val.length / 48))}
                      className="w-full resize-y rounded-panel border border-transparent bg-transparent p-1.5 hover:border-mist focus:border-fg"
                      style={{ borderBottomColor: l.hue }}
                    />
                    <span className="mt-1 block text-xs text-slate" role="status">
                      {status[tr.id] ?? (tr.edited ? "Edited" : "")}
                      {tr.fit_speed && tr.fit_speed > 1.01 ? `${status[tr.id] || tr.edited ? " · " : ""}sped up ${tr.fit_speed.toFixed(2)}x to fit` : ""}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2">
                      <button aria-label={`Play from ${s.start_s.toFixed(1)} s`} onClick={() => onPlay(s.start_s)} className="grid size-9 place-items-center rounded-chip border border-mist hover:border-fg">
                        <svg width="12" height="12" viewBox="0 0 16 16" aria-hidden><path d="M4 2.5v11l9-5.5z" fill="currentColor" /></svg>
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
      {toast && <div role="status" className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-chip bg-fg px-5 py-2.5 text-on-fg">{toast}</div>}
    </section>
  );
}
