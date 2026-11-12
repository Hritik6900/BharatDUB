"use client";
import { useEffect, useState } from "react";
import { Nav } from "@/components/layout/Nav";
import { api, fmtSeconds, type Dashboard } from "@/lib/api";
import { lang } from "@/lib/langs";

function Tile({ label, value, sub }: { label: string; value: string | null; sub?: string }) {
  return (
    <div className="rounded-panel border border-mist bg-surface p-5">
      <p className="text-sm text-slate">{label}</p>
      <p className="tnum mt-1 font-display text-[2.441rem] font-semibold leading-tight">{value ?? <span className="text-slate">Not measured yet</span>}</p>
      {sub && <p className="text-sm text-slate">{sub}</p>}
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
    <>
      <Nav />
      <main className="mx-auto max-w-6xl px-4 py-12 sm:px-8 sm:py-16">
        <h1 className="font-display text-[clamp(2rem,5vw,3rem)] font-semibold leading-tight">Dashboard</h1>
        <p className="mt-3 text-slate">Every number here is measured from real jobs and live chunks. Blank means not measured yet.</p>
        {err && <p role="alert" className="mt-6">{err}</p>}
        {d && (
          <>
            {d.mock_providers && <p className="mt-6 rounded-panel border border-[var(--hi)] px-4 py-3 text-sm">Mock mode: these numbers come from simulated providers, not Gnani.</p>}
            <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Tile label="Minutes dubbed" value={d.studio.minutes_dubbed != null ? d.studio.minutes_dubbed.toFixed(1) : null} sub="video minutes × languages" />
              <Tile label="Median Studio turnaround" value={d.studio.median_turnaround_s != null ? fmtSeconds(d.studio.median_turnaround_s) : null} sub={`${d.studio.jobs_done} of ${d.studio.jobs} jobs finished`} />
              <Tile label="Live median delay" value={d.live.p50_ms != null ? `${(d.live.p50_ms / 1000).toFixed(1)} s` : null} sub="speech end to first dubbed audio" />
              <Tile label="Live p95 delay" value={d.live.p95_ms != null ? `${(d.live.p95_ms / 1000).toFixed(1)} s` : null} sub={`${d.live.chunks} chunks · ${d.live.sessions} sessions`} />
            </div>

            <section className="mt-12" aria-labelledby="langs-h">
              <h2 id="langs-h" className="font-display text-xl font-semibold">Rendered videos by language</h2>
              {langs.length ? (
                <table className="mt-5 w-full max-w-2xl">
                  <caption className="sr-only">Number of rendered videos per language</caption>
                  <tbody>
                    {langs.map(([code, n]) => (
                      <tr key={code}>
                        <th scope="row" className="w-32 py-1.5 pr-4 text-left font-normal">
                          <span className="mr-2 inline-block size-2.5 rounded-full align-middle" style={{ background: lang(code).hue }} />
                          {lang(code).name}
                        </th>
                        <td className="py-1.5">
                          <div className="flex items-center gap-3" title={`${lang(code).name}: ${n}`}>
                            <div className="h-5 rounded-r-[4px] bg-fg" style={{ width: `${(n / max) * 100}%`, minWidth: 4 }} />
                            <span className="tnum text-sm text-fg">{n}</span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="mt-3 text-sm text-slate">No rendered videos yet.</p>
              )}
            </section>
            <p className="mt-12 text-sm text-slate">{d.languages_supported} Indian languages supported.</p>
          </>
        )}
      </main>
    </>
  );
}
