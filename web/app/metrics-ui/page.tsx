"use client";
import { useCallback, useEffect, useState } from "react";
import { ChartNoAxesColumn, RefreshCw } from "lucide-react";
import { Shell } from "@/components/layout/Shell";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { api } from "@/lib/api";
import { lang } from "@/lib/langs";

interface Cost {
  currency: string;
  rates_set: string[];
  rates_missing: string[];
  total: number | null;
  per_minute: number | null;
  parts: Record<string, number | null>;
}
interface LiveBlock {
  phrases: number;
  spoken: number;
  skipped_late: number;
  first_audio_p50_ms: number | null;
  first_audio_p95_ms: number | null;
  heard_p50_ms: number | null;
  heard_p95_ms: number | null;
  translate_p50_ms: number | null;
  on_time_pct: number | null;
  within_1s_pct: number | null;
  timed: number;
  copied_voice_pct: number | null;
  fallback_pct: { stt: number | null; llm: number | null; tts: number | null };
}
interface Summary {
  trace_on: boolean;
  hours: number;
  records: number;
  live: LiveBlock & {
    per_lang: Record<string, LiveBlock>;
    per_engine: Record<string, LiveBlock>;
    viewer_reports: number;
    viewer_within_1s_pct: number | null;
    usage: { stream_minutes: number; sessions: number; gpu_seconds: number };
    cost: Cost;
  };
  studio: {
    jobs: number;
    lines: number;
    flagged: number;
    backcheck_mean_pct: number | null;
    backchecked: number;
    similarity_mean: number | null;
    similarity_n: number;
    speed_max: number | null;
    within_115_pct: number | null;
    fallback_pct: number | null;
    turnaround_p50_s: number | null;
    usage: { dubbed_minutes: number; jobs: number; gpu_seconds: number };
    cost: Cost;
  };
}

const secs = (ms: number | null) => (ms == null ? null : `${(ms / 1000).toFixed(1)} s`);
const pct = (v: number | null) => (v == null ? null : `${v}%`);
const RATE_NAMES: Record<string, string> = { gpu: "GPU", hosted_stt: "hosted speech-to-text", hosted_tts: "hosted voice", hosted_llm: "hosted translation" };

function Tile({ label, value, sub }: { label: string; value: string | null; sub?: string }) {
  return (
    <div className="card flex flex-col p-5">
      <p className="eyebrow">{label}</p>
      <p className="tnum h-display mt-4 text-4xl">{value ?? <span className="font-sans text-base tracking-normal text-muted">Not measured</span>}</p>
      {sub && <p className="mt-2 text-sm text-muted">{sub}</p>}
    </div>
  );
}

function CostLine({ c, minutes, unit }: { c: Cost; minutes: number; unit: string }) {
  if (c.per_minute == null) {
    return <p className="mt-3 text-sm text-muted">No cost shown: no rate is set (the GPU price per hour and the hosted prices are settings).</p>;
  }
  return (
    <p className="mt-3 text-sm">
      <span className="tnum font-mono font-semibold">{c.per_minute.toFixed(4)} {c.currency}</span> per {unit}, over {minutes} minutes.
      <span className="ml-2 text-muted">
        Counted: {c.rates_set.map((r) => RATE_NAMES[r] ?? r).join(", ")}.
        {c.rates_missing.length > 0 && <> Not counted (no rate set): {c.rates_missing.map((r) => RATE_NAMES[r] ?? r).join(", ")}.</>}
      </span>
    </p>
  );
}

function LiveTable({ title, rows, name }: { title: string; rows: Record<string, LiveBlock>; name: (k: string) => string }) {
  const keys = Object.keys(rows);
  if (!keys.length) return null;
  return (
    <div className="mt-6 overflow-x-auto">
      <table className="w-full min-w-[640px] text-sm">
        <caption className="eyebrow pb-2 text-left">{title}</caption>
        <thead>
          <tr className="text-left text-muted">
            <th scope="col" className="py-1.5 pr-4 font-normal">&nbsp;</th>
            <th scope="col" className="py-1.5 pr-4 font-normal">Phrases</th>
            <th scope="col" className="py-1.5 pr-4 font-normal">First audio p50 / p95</th>
            <th scope="col" className="py-1.5 pr-4 font-normal">Within 0.25 s / 1 s</th>
            <th scope="col" className="py-1.5 pr-4 font-normal">Skipped</th>
            <th scope="col" className="py-1.5 font-normal">Copied voice</th>
          </tr>
        </thead>
        <tbody>
          {keys.map((k) => {
            const b = rows[k];
            return (
              <tr key={k} className="border-t border-line">
                <th scope="row" className="py-2 pr-4 text-left font-medium">{name(k)}</th>
                <td className="tnum py-2 pr-4 font-mono">{b.phrases}</td>
                <td className="tnum py-2 pr-4 font-mono">{secs(b.first_audio_p50_ms) ?? "-"} / {secs(b.first_audio_p95_ms) ?? "-"}</td>
                <td className="tnum py-2 pr-4 font-mono">{pct(b.on_time_pct) ?? "-"} / {pct(b.within_1s_pct) ?? "-"}</td>
                <td className="tnum py-2 pr-4 font-mono">{b.skipped_late}</td>
                <td className="tnum py-2 font-mono">{pct(b.copied_voice_pct) ?? "-"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function MetricsPage() {
  const [d, setD] = useState<Summary | null>(null);
  const [err, setErr] = useState("");
  const [hours, setHours] = useState(24);
  const load = useCallback(() => {
    api<Summary>(`/api/v1/metrics/summary?hours=${hours}`).then((x) => { setD(x); setErr(""); }).catch((e) => setErr((e as Error).message));
  }, [hours]);
  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load]);
  const fb = d?.live.fallback_pct;
  return (
    <Shell>
      <div className="mx-auto max-w-6xl px-5 pb-24 pt-12 sm:px-8 sm:pt-16">
        <PageHeader
          icon={ChartNoAxesColumn}
          eyebrow="Numbers"
          title={<>From the <em>trace</em></>}
          lede="Every figure is computed from the trace of real phrases and lines. A blank means it was not measured."
        />
        <div className="mt-8 flex flex-wrap items-center gap-3">
          <label className="text-sm text-muted" htmlFor="hours">Window</label>
          <select id="hours" value={hours} onChange={(e) => setHours(Number(e.target.value))} className="rounded-chip border border-line bg-surface px-3 py-1.5 text-sm">
            <option value={1}>Last hour</option>
            <option value={6}>Last 6 hours</option>
            <option value={24}>Last 24 hours</option>
            <option value={168}>Last 7 days</option>
          </select>
          <button type="button" onClick={load} className="inline-flex items-center gap-2 rounded-chip border border-line bg-surface px-3 py-1.5 text-sm hover:bg-fg/5">
            <RefreshCw aria-hidden className="size-3.5" /> Refresh
          </button>
          {d && <span className="text-sm text-muted">{d.records} trace records</span>}
        </div>
        {err && <div className="mt-6"><Notice tone="error" role="alert">{err}</Notice></div>}
        {d && !d.trace_on && <div className="mt-6"><Notice tone="warn">The trace is switched off (V1_TRACE), so nothing new is being recorded.</Notice></div>}
        {d && (
          <div className="rise">
            <h2 className="eyebrow mt-10">Live</h2>
            <div className="mt-3 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
              <Tile label="First audio, median" value={secs(d.live.first_audio_p50_ms)} sub={`p95 ${secs(d.live.first_audio_p95_ms) ?? "not measured"} · end of phrase to first dubbed audio`} />
              <Tile label="On time" value={pct(d.live.on_time_pct)} sub={`within 0.25 s of the video moment · within 1 s: ${pct(d.live.within_1s_pct) ?? "not measured"} · ${d.live.timed} timed phrases`} />
              <Tile label="Viewers, within 1 s" value={pct(d.live.viewer_within_1s_pct)} sub={`${d.live.viewer_reports} reports from viewers' players`} />
              <Tile label="Fallback rate" value={fb ? pct(Math.max(fb.stt ?? 0, fb.llm ?? 0, fb.tts ?? 0)) : null} sub={fb ? `speech ${pct(fb.stt) ?? "-"} · translation ${pct(fb.llm) ?? "-"} · voice ${pct(fb.tts) ?? "-"}` : undefined} />
            </div>
            <section className="card mt-5 p-6" aria-label="Live detail">
              <p className="text-sm text-muted">
                {d.live.phrases} phrase-languages over {d.live.usage.sessions} sessions and {d.live.usage.stream_minutes} minutes of stream; {d.live.skipped_late} skipped as too late;
                translation median {secs(d.live.translate_p50_ms) ?? "not measured"}; {d.live.usage.gpu_seconds} s of work reported by our GPU servers.
              </p>
              <CostLine c={d.live.cost} minutes={d.live.usage.stream_minutes} unit="stream minute" />
              <LiveTable title="By language" rows={d.live.per_lang} name={(k) => lang(k).name} />
              <LiveTable title="By engine" rows={d.live.per_engine} name={(k) => (k === "gpu" ? "GPU engine" : "Standard")} />
            </section>

            <h2 className="eyebrow mt-10">Studio</h2>
            <div className="mt-3 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
              <Tile label="Words heard back" value={pct(d.studio.backcheck_mean_pct)} sub={`${d.studio.backchecked} lines checked`} />
              <Tile label="Voice similarity" value={d.studio.similarity_mean != null ? d.studio.similarity_mean.toFixed(2) : null} sub={`${d.studio.similarity_n} lines scored`} />
              <Tile label="Largest speed-up" value={d.studio.speed_max != null ? `${d.studio.speed_max.toFixed(2)}x` : null} sub={`within 1.15x: ${pct(d.studio.within_115_pct) ?? "not measured"}`} />
              <Tile label="Flagged lines" value={d.studio.lines ? String(d.studio.flagged) : null} sub={`of ${d.studio.lines} lines in ${d.studio.jobs} jobs`} />
            </div>
            <section className="card mt-5 p-6" aria-label="Studio detail">
              <p className="text-sm text-muted">
                Median turnaround {d.studio.turnaround_p50_s != null ? `${d.studio.turnaround_p50_s} s` : "not measured"}; {d.studio.usage.dubbed_minutes} dubbed minutes;
                fallback voice on {pct(d.studio.fallback_pct) ?? "no measured share of"} lines.
              </p>
              <CostLine c={d.studio.cost} minutes={d.studio.usage.dubbed_minutes} unit="dubbed minute" />
            </section>
          </div>
        )}
      </div>
    </Shell>
  );
}
