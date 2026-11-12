"use client";
import { useMemo, useState } from "react";

/** Single-series latency line (ink), crosshair + tooltip on hover. Values in ms. */
export function Sparkline({ values, height = 72, label = "Dub delay per chunk" }: { values: number[]; height?: number; label?: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 600;
  const pts = useMemo(() => {
    if (!values.length) return [];
    const max = Math.max(...values, 1000);
    const step = values.length > 1 ? W / (values.length - 1) : 0;
    return values.map((v, i) => [i * step, height - 6 - (v / max) * (height - 14)] as const);
  }, [values, height]);
  if (!values.length) return <p className="text-sm text-slate">No chunks yet.</p>;
  const d = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const h = hover != null ? pts[hover] : null;
  return (
    <figure className="relative">
      <svg
        viewBox={`0 0 ${W} ${height}`}
        preserveAspectRatio="none"
        className="block h-[72px] w-full"
        role="img"
        aria-label={`${label}: latest ${(values[values.length - 1] / 1000).toFixed(1)} s`}
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          const i = Math.round(((e.clientX - r.left) / r.width) * (values.length - 1));
          setHover(Math.max(0, Math.min(values.length - 1, i)));
        }}
      >
        <line x1="0" x2={W} y1={height - 6} y2={height - 6} stroke="var(--mist)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
        <path d={d} fill="none" stroke="var(--fg)" strokeWidth="2" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
        {h && (
          <>
            <line x1={h[0]} x2={h[0]} y1="0" y2={height} stroke="var(--slate)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
            <circle cx={h[0]} cy={h[1]} r="4" fill="var(--fg)" stroke="var(--bg)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
          </>
        )}
      </svg>
      {hover != null && (
        <div
          className="tnum pointer-events-none absolute -top-8 rounded-panel border border-mist bg-surface px-2 py-0.5 text-xs"
          style={{ left: `${(hover / Math.max(1, values.length - 1)) * 100}%`, transform: "translateX(-50%)" }}
        >
          Chunk {hover + 1}: {(values[hover] / 1000).toFixed(2)} s
        </div>
      )}
    </figure>
  );
}
