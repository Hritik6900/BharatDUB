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
  flags: Record<string, boolean | string>;
  gpu: { name: string; used_gb: number; free_gb: number; total_gb: number } | null;
  gpu_reported_gb: number | null;
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
  const on = h ? Object.entries(h.flags).filter(([, v]) => v === true).map(([k]) => k) : [];
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

            <section className="card mt-5 p-6" aria-label="GPU memory">
              <h2 className="eyebrow">GPU memory</h2>
              {h.gpu ? (
                <p className="mt-3">
                  <span className="tnum h-display text-4xl">{h.gpu.free_gb.toFixed(1)} GB</span>
                  <span className="ml-3 text-sm text-muted">free of {h.gpu.total_gb.toFixed(1)} GB ({h.gpu.used_gb.toFixed(1)} GB in use) on the card of the machine this backend runs on: {h.gpu.name}</span>
                </p>
              ) : (
                <p className="mt-3 text-sm text-muted">
                  Not measured here: the machine this backend runs on has no GPU.
                  {h.gpu_reported_gb != null && <> The servers that report it hold {h.gpu_reported_gb} GB in tensors (less than their process totals).</>}
                </p>
              )}
            </section>

            <section className="card mt-5 p-6" aria-label="Flags">
              <h2 className="eyebrow">New behaviour switched on</h2>
              <p className="mt-3 text-sm">
                {on.length ? <span className="font-mono">{on.join(" · ")}</span> : <span className="text-muted">None. This version behaves like the other one.</span>}
                <span className="ml-3 text-muted">Store: {String(h.flags.V1_STORE)}</span>
              </p>
            </section>
          </div>
        )}
      </div>
    </Shell>
  );
}
