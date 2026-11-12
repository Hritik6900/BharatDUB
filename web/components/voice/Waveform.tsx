"use client";
import { useId } from "react";

/** Speech-like amplitude envelope (deterministic), 0..1. Illustration only, not data. */
export function speechEnvelope(n: number, seed = 7): number[] {
  let s = seed;
  const rnd = () => ((s = (s * 16807) % 2147483647) / 2147483647);
  const out: number[] = [];
  let word = 0;
  for (let i = 0; i < n; i++) {
    if (word <= 0) word = 6 + Math.floor(rnd() * 14);
    const inWord = (i % 23) > 2;
    word--;
    out.push(inWord ? 0.25 + 0.75 * Math.abs(Math.sin(i * 0.55)) * (0.5 + rnd() * 0.5) : 0.06 + rnd() * 0.06);
  }
  return out;
}

interface Props {
  samples: number[];
  hue?: string;
  toHue?: string;
  height?: number;
  className?: string;
  strokeWidth?: number;
  gain?: number;
  label?: string;
}

/** Single-line waveform: a voice drawn as one stroke, coloured from source hue to target hue. */
export function Waveform({ samples, hue = "var(--hi)", toHue, height = 120, className = "", strokeWidth = 2.5, gain = 1, label }: Props) {
  const id = useId().replace(/:/g, "");
  const W = 1000;
  const mid = height / 2;
  const step = W / Math.max(1, samples.length - 1);
  let d = `M0,${mid}`;
  samples.forEach((a, i) => {
    const amp = Math.min(1, a * gain) * (mid - strokeWidth);
    const x = i * step;
    const y = mid + (i % 2 ? amp : -amp);
    const cx = x - step / 2;
    d += ` Q${cx.toFixed(1)},${y.toFixed(1)} ${x.toFixed(1)},${mid}`;
  });
  return (
    <svg viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none" className={`block w-full ${className}`} style={{ height }} role={label ? "img" : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      <defs>
        <linearGradient id={`g${id}`} x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" style={{ stopColor: hue, transition: "stop-color .7s" }} />
          <stop offset="1" style={{ stopColor: toHue ?? hue, transition: "stop-color .7s" }} />
        </linearGradient>
      </defs>
      <path d={d} fill="none" stroke={`url(#g${id})`} strokeWidth={strokeWidth} vectorEffect="non-scaling-stroke" strokeLinecap="round" />
    </svg>
  );
}
