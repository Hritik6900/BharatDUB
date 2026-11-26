"use client";
import { useCallback, useEffect, useState } from "react";
import { Activity, CircleCheck, CircleX, RefreshCw } from "lucide-react";
import { Shell } from "@/components/layout/Shell";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { api } from "@/lib/api";

interface Check {
  name: string;
  kind: "shared" | "v1" | "hosted";
  ok: boolean;
  ms?: number;
  url?: string;
  error?: string;
  configured?: boolean;
  info?: Record<string, string | number | boolean>;
}
interface V1Health {
  ok: boolean;
  checks: Check[];
  // A diagnostic for the people who run the server. The page shows the mode and the store, never a list of switches.
  flags: Record<string, unknown>;
  // The model servers' card, as the GPU machine itself reports it. null = unknown (never this PC's own card).
  gpu: { name?: string; used_gb: number; free_gb: number; total_gb: number; util_pct?: number; temp_c?: number; power_w?: number; processes?: { name: string; used_gb: number | null }[] } | null;
  gpu_name?: string;
  gpu_reported_gb: number | null;
  circuits?: { name: string; state: "closed" | "open" | "half_open"; opens: number; down_s?: number; reason?: string }[];
  mock_providers: boolean;
}

const GROUPS: { kind: Check["kind"]; title: string; note: string }[] = [
  { kind: "v1", title: "v1 services", note: "Run by this version only." },
  { kind: "shared", title: "Shared GPU servers", note: "Also used by the other version. Called, never changed." },
  { kind: "hosted", title: "Hosted services", note: "Reachable means the service answers; no key is sent by this check." },
];

function Row({ c }: { c: Check }) {
  const Icon = c.ok ? CircleCheck : CircleX;
  const info = c.info ? Object.entries(c.info).map(([k, v]) => `${k} ${v}`).join(" · ") : "";
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line py-3 first:border-t-0">
      <Icon aria-hidden className={`size-5 shrink-0 ${c.ok ? "text-ok" : "text-danger"}`} />
      <span className="min-w-48 flex-1 font-medium">{c.name}</span>
      <span className={`text-sm ${c.ok ? "text-muted" : "text-danger"}`}>{c.ok ? "answers" : c.error ?? "down"}</span>
      {c.ms != null && <span className="tnum w-20 text-right font-mono text-sm text-muted">{c.ms} ms</span>}
      {info && <span className="w-full pl-9 font-mono text-xs text-muted">{info}</span>}
    </li>
  );
}

export default function HealthPage() {
  const [h, setH] = useState<V1Health | null>(null);
  const [err, setErr] = useState("");
  const [at, setAt] = useState("");
  const load = useCallback(() => {
    api<V1Health>("/api/v1/health")
      .then((d) => {
        setH(d);
        setErr("");
        setAt(new Date().toLocaleTimeString());
      })
      .catch((e) => setErr((e as Error).message));
  }, []);
  useEffect(() => {
    load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, [load]);
  const manual = h ? h.flags.V1_MODE === "manual" : false;
  const pinned = h && h.flags.overrides && typeof h.flags.overrides === "object" ? Object.keys(h.flags.overrides as object).length : 0;
  return (
    <Shell>
      <div className="mx-auto max-w-4xl px-5 pb-24 pt-12 sm:px-8 sm:pt-16">
        <PageHeader
          icon={Activity}
          eyebrow="Status"
          title={<>Is everything <em>up</em>?</>}
          lede="Each service is asked once every ten seconds. Times are measured by this check."
        />
        {err && <div className="mt-8"><Notice tone="error" role="alert">{err}</Notice></div>}
        {h && (
          <div className="rise">
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <span className={`inline-flex items-center gap-2 rounded-chip border px-3 py-1.5 text-sm font-semibold ${h.ok ? "border-line bg-surface" : "border-danger text-danger"}`}>
                {h.ok ? <CircleCheck aria-hidden className="size-4 text-ok" /> : <CircleX aria-hidden className="size-4" />}
                {h.ok ? "All services answer" : "Something is down"}
              </span>
              <button type="button" onClick={load} className="inline-flex items-center gap-2 rounded-chip border border-line bg-surface px-3 py-1.5 text-sm hover:bg-fg/5">
                <RefreshCw aria-hidden className="size-3.5" /> Check now
              </button>
              {at && <span className="text-sm text-muted">Last checked {at}</span>}
            </div>
            {h.mock_providers && <div className="mt-5"><Notice tone="warn">Mock mode: the hosted services are simulated.</Notice></div>}

            {GROUPS.map((g) => {
              const rows = h.checks.filter((c) => c.kind === g.kind);
              if (!rows.length) return null;
              return (
                <section key={g.kind} className="card mt-5 p-6" aria-label={g.title}>
                  <h2 className="eyebrow">{g.title}</h2>
                  <p className="mt-1 text-sm text-muted">{g.note}</p>
                  <ul className="mt-3">{rows.map((c) => <Row key={c.name} c={c} />)}</ul>
                </section>
              );
            })}

            <section className="card mt-5 p-6" aria-label="GPU">
              <h2 className="eyebrow">GPU: {h.gpu_name ?? "A100 (VM)"}</h2>
              {h.gpu ? (
                <>
                  <p className="mt-3">
                    <span className="tnum h-display text-4xl">{h.gpu.free_gb.toFixed(1)} GB</span>
                    <span className="ml-3 text-sm text-muted">
                      free of {h.gpu.total_gb.toFixed(1)} GB ({h.gpu.used_gb.toFixed(1)} GB in use)
                      {h.gpu.util_pct != null && <>, {h.gpu.util_pct}% busy</>}
                      {h.gpu.temp_c != null && <>, {h.gpu.temp_c} °C</>}
                      {h.gpu.power_w != null && <>, {Math.round(h.gpu.power_w)} W</>}
                      {h.gpu.name && <>. Reported by the GPU machine: {h.gpu.name}</>}
                    </span>
                  </p>
                  {!!h.gpu.processes?.length && (
                    <p className="mt-2 font-mono text-xs text-muted">{h.gpu.processes.map((x) => `${x.name} ${x.used_gb ?? "?"} GB`).join(" · ")}</p>
                  )}
                </>
              ) : (
                <p className="mt-3">
                  <span className="h-display text-2xl">{h.gpu_name ?? "A100 (VM)"}: unknown</span>
                  <span className="mt-2 block text-sm text-muted">
                    The models run on a GPU machine that this page cannot see into yet: no server there reports the card.
                    {h.gpu_reported_gb != null && <> The servers that say so hold {h.gpu_reported_gb} GB in tensors (less than their process totals).</>}
                  </span>
                </p>
              )}
            </section>

            {!!h.circuits?.length && (
              <section className="card mt-5 p-6" aria-label="Circuit breakers">
                <h2 className="eyebrow">Circuit breakers</h2>
                <p className="mt-1 text-sm text-muted">An endpoint that stops answering is left alone for a while and the next provider answers; it is tried again by itself.</p>
                <ul className="mt-3">
                  {h.circuits.map((c) => (
                    <li key={c.name} className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line py-3 first:border-t-0">
                      {c.state === "closed" ? <CircleCheck aria-hidden className="size-5 shrink-0 text-ok" /> : <CircleX aria-hidden className="size-5 shrink-0 text-danger" />}
                      <span className="min-w-48 flex-1 font-medium">{c.name}</span>
                      <span className={`text-sm ${c.state === "closed" ? "text-muted" : "text-danger"}`}>
                        {c.state === "closed" ? "in use" : c.state === "open" ? `not called, for ${Math.round(c.down_s ?? 0)} s now` : `being tried again after ${Math.round(c.down_s ?? 0)} s`}
                      </span>
                      <span className="tnum w-28 text-right font-mono text-sm text-muted">opened {c.opens}x</span>
                      {c.state !== "closed" && c.reason && <span className="w-full pl-9 font-mono text-xs text-muted">{c.reason}</span>}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <section className="card mt-5 p-6" aria-label="How this server runs">
              <h2 className="eyebrow">How this server runs</h2>
              <p className="mt-3 text-sm">
                {manual ? "Set up by hand for a measurement: its behaviour is not what the product normally does." : "Automatic: the server decides by itself what each stream and video needs."}
                {!manual && pinned > 0 && <span className="ml-1">{pinned === 1 ? "One behaviour is" : `${pinned} behaviours are`} held back by the operator.</span>}
                <span className="ml-3 text-muted">Store: {String(h.flags.V1_STORE)}</span>
              </p>
            </section>
          </div>
        )}
      </div>
    </Shell>
  );
}
