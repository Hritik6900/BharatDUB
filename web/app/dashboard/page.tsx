"use client";
import { useEffect, useState } from "react";
import { Clapperboard, Gauge, Hourglass, Languages, LayoutDashboard, Timer, type LucideIcon } from "lucide-react";
import { Shell } from "@/components/layout/Shell";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { api, fmtSeconds, type Dashboard } from "@/lib/api";
import { lang } from "@/lib/langs";

function Tile({ icon: Icon, label, value, sub }: { icon: LucideIcon; label: string; value: string | null; sub?: string }) {
  return (
    <div className="card flex flex-col p-6">
      <div className="flex items-center justify-between">
        <p className="eyebrow">{label}</p>
        <Icon aria-hidden className="size-4 text-muted" />
      </div>
      <p className="tnum h-display mt-6 text-[3.25rem]">{value ?? <span className="font-sans text-lg tracking-normal text-muted">Not measured yet</span>}</p>
      {sub && <p className="mt-2 text-sm text-muted">{sub}</p>}
    </div>
  );
}

export default function DashboardPage() {
  const [d, setD] = useState<Dashboard | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    api<Dashboard>("/api/dashboard").then(setD).catch((e) => setErr((e as Error).message));
  }, []);
  const langs = d ? Object.entries(d.studio.languages).sort((a, b) => b[1] - a[1]) : [];
  const max = Math.max(1, ...langs.map(([, n]) => n));
  return (
    <Shell>
      <div className="mx-auto max-w-6xl px-5 pb-24 pt-12 sm:px-8 sm:pt-16">
        <PageHeader
          icon={LayoutDashboard}
          eyebrow="Dashboard"
          title={<>Measured, <em>not promised</em></>}
          lede="Every number here is measured from real jobs and live chunks. Blank means not measured yet."
        />
        {err && <div className="mt-8"><Notice tone="error" role="alert">{err}</Notice></div>}
        {d && (
          <div className="rise">
            {d.mock_providers && <div className="mt-8"><Notice tone="warn">Mock mode: these numbers come from simulated providers, not Gnani.</Notice></div>}
            <div className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
              <Tile icon={Clapperboard} label="Minutes dubbed" value={d.studio.minutes_dubbed != null ? d.studio.minutes_dubbed.toFixed(1) : null} sub="video minutes × languages" />
              <Tile icon={Hourglass} label="Studio turnaround" value={d.studio.median_turnaround_s != null ? fmtSeconds(d.studio.median_turnaround_s) : null} sub={`median · ${d.studio.jobs_done} of ${d.studio.jobs} jobs finished`} />
              <Tile icon={Timer} label="Live median delay" value={d.live.p50_ms != null ? `${(d.live.p50_ms / 1000).toFixed(1)} s` : null} sub="speech end to first dubbed audio" />
              <Tile icon={Gauge} label="Live p95 delay" value={d.live.p95_ms != null ? `${(d.live.p95_ms / 1000).toFixed(1)} s` : null} sub={`${d.live.chunks} chunks · ${d.live.sessions} sessions`} />
            </div>

            <section className="card mt-5 p-6 sm:p-8" aria-labelledby="langs-h">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 id="langs-h" className="eyebrow">Rendered videos by language</h2>
                <p className="flex items-center gap-2 text-sm text-muted">
                  <Languages aria-hidden className="size-4" />
                  {d.languages_supported} Indian languages supported
                </p>
              </div>
              {langs.length ? (
                <table className="mt-6 w-full">
                  <caption className="sr-only">Number of rendered videos per language</caption>
                  <tbody>
                    {langs.map(([code, n]) => (
                      <tr key={code}>
                        <th scope="row" className="w-36 whitespace-nowrap py-2 pr-4 text-left font-normal">
                          <span className="mr-2.5 inline-block size-2.5 rounded-full align-middle" style={{ background: lang(code).hue }} />
                          {lang(code).name}
                        </th>
                        <td className="py-2">
                          <div className="flex items-center gap-3" title={`${lang(code).name}: ${n}`}>
                            <div className="h-6 rounded-r-[6px] rounded-l-[2px] bg-fg" style={{ width: `${(n / max) * 100}%`, minWidth: 4 }} />
                            <span className="tnum font-mono text-sm">{n}</span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="mt-5 text-sm text-muted">No rendered videos yet.</p>
              )}
            </section>
          </div>
        )}
      </div>
    </Shell>
  );
}
