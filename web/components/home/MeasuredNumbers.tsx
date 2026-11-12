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
          duration: 0.8,
          ease: "power3.out",
          scrollTrigger: { trigger: el, start: "top 85%", once: true },
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
    <section ref={root} aria-label="Measured results" className="border-y border-mist">
      <dl className="mx-auto grid max-w-6xl gap-10 px-4 py-16 sm:grid-cols-3 sm:px-8">
        {stats.map((s) => (
          <div key={s.label}>
            <dt className="text-slate">{s.label}</dt>
            <dd className="tnum font-display text-[3.815rem] font-semibold leading-none">
              <span data-count={s.value} data-dec={s.decimals}>{s.value.toFixed(s.decimals)}</span>
              <span className="ml-1 text-[1.563rem] text-slate">{s.unit}</span>
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
