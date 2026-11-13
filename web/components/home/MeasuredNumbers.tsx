"use client";
import { useEffect, useRef, useState } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";
import { api, type Dashboard } from "@/lib/api";
import { useReducedMotion } from "@/lib/hooks";

gsap.registerPlugin(ScrollTrigger, useGSAP);

interface Stat {
  value: number;
  decimals: number;
  unit: string;
  label: string;
}

/** Up to three measured numbers. Hidden until real (non-mock) measurements exist. */
export function MeasuredNumbers() {
  const [stats, setStats] = useState<Stat[] | null>(null);
  const root = useRef<HTMLElement>(null);
  const reduced = useReducedMotion();

  useEffect(() => {
    api<Dashboard>("/api/dashboard")
      .then((d) => {
        if (d.mock_providers) return;
        const s: Stat[] = [];
        if (d.studio.median_turnaround_s != null) s.push({ value: d.studio.median_turnaround_s, decimals: 0, unit: "s", label: "median Studio turnaround" });
        if (d.live.p50_ms != null) s.push({ value: d.live.p50_ms / 1000, decimals: 1, unit: "s", label: "median Live dub delay" });
        if (s.length) s.push({ value: d.languages_supported, decimals: 0, unit: "", label: "Indian languages" });
        setStats(s.length ? s : null);
      })
      .catch(() => setStats(null));
  }, []);

  useGSAP(
    () => {
      if (!stats || reduced) return;
      gsap.utils.toArray<HTMLElement>("[data-count]").forEach((el) => {
        const end = Number(el.dataset.count);
        const dec = Number(el.dataset.dec);
        const o = { v: 0 };
        gsap.to(o, {
          v: end,
          duration: 1,
          ease: "power3.out",
          scrollTrigger: { trigger: el, start: "top 88%", once: true },
          onUpdate: () => {
            el.textContent = o.v.toFixed(dec);
          },
        });
      });
    },
    { scope: root, dependencies: [stats, reduced] },
  );

  if (!stats) return null;
  return (
    <section ref={root} aria-label="Measured results" className="mx-auto max-w-6xl px-5 sm:px-8">
      <p className="eyebrow">Measured, not promised</p>
      <dl className="mt-6 grid gap-5 sm:grid-cols-3">
        {stats.map((s) => (
          <div key={s.label} className="card p-7">
            <dd className="tnum h-display text-[4.5rem]">
              <span data-count={s.value} data-dec={s.decimals}>{s.value.toFixed(s.decimals)}</span>
              <span className="ml-1 text-[1.75rem] text-muted">{s.unit}</span>
            </dd>
            <dt className="mt-2 text-muted">{s.label}</dt>
          </div>
        ))}
      </dl>
    </section>
  );
}
