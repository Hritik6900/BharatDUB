"use client";
import { useEffect, useRef } from "react";

interface Props {
  /** Real audio: bars follow its spectrum. Without it the bars draw a speech-like illustration. */
  analyser?: AnalyserNode | null;
  /** Illustration mode only: false = flat line. */
  active?: boolean;
  bars?: number;
  height?: number;
  /** CSS colours or custom properties ("--hi" or "var(--hi)"), drawn as a left-to-right gradient. */
  colors?: string[];
  className?: string;
  seed?: number;
}

/** Mirrored voice bars on a canvas. */
export function VoiceBars({ analyser = null, active = true, bars = 48, height = 56, colors = ["--hi", "--bn", "--te"], className = "", seed = 0 }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  const live = useRef({ analyser, active });
  live.current = { analyser, active };
  const colorKey = colors.join("|");

  useEffect(() => {
    const cv = ref.current;
    const g = cv?.getContext("2d");
    if (!cv || !g) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const cs = getComputedStyle(cv);
    const resolved = colorKey.split("|").map((c) => {
      const name = c.match(/--[\w-]+/)?.[0];
      return name ? cs.getPropertyValue(name).trim() || "#888" : c;
    });
    const vals = new Float32Array(bars);
    let freq = new Uint8Array(0);
    let raf = 0;
    const mid = (bars - 1) / 2;

    const draw = (ms: number) => {
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const w = cv.clientWidth;
      const h = cv.clientHeight;
      if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
        cv.width = Math.round(w * dpr);
        cv.height = Math.round(h * dpr);
      }
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, w, h);
      const t = ms / 1000 + seed;
      const { analyser: an, active: on } = live.current;
      if (an) {
        if (freq.length !== an.frequencyBinCount) freq = new Uint8Array(an.frequencyBinCount);
        an.getByteFrequencyData(freq);
      }
      const grad = g.createLinearGradient(0, 0, w, 0);
      resolved.forEach((c, i) => grad.addColorStop(resolved.length === 1 ? 0 : i / (resolved.length - 1), c));
      g.fillStyle = grad;
      const step = w / bars;
      const bw = Math.max(2, step * 0.5);
      for (let i = 0; i < bars; i++) {
        const d = Math.abs(i - mid) / mid; // 0 at the centre, 1 at the edges
        let target = 0.05;
        if (an) {
          const bin = Math.floor(2 + d * d * Math.min(freq.length - 3, 160));
          target = Math.max(0.05, Math.pow(freq[bin] / 255, 1.5));
        } else if (on) {
          const phrase = 0.3 + 0.7 * Math.pow(Math.abs(Math.sin(t * 1.25 + Math.sin(t * 0.55) * 2)), 1.4);
          const shape = 1 - Math.pow(d, 1.6) * 0.78;
          target = 0.07 + 0.93 * phrase * shape * Math.abs(Math.sin(t * 4.1 + i * 0.55) * Math.cos(t * 2.2 + i * 0.21));
        }
        vals[i] += (target - vals[i]) * (reduced ? 1 : 0.2);
        const bh = Math.max(bw, vals[i] * h);
        g.beginPath();
        g.roundRect(i * step + (step - bw) / 2, (h - bh) / 2, bw, bh, bw / 2);
        g.fill();
      }
      if (!reduced) raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [bars, colorKey, seed]);

  return <canvas ref={ref} aria-hidden className={`block w-full ${className}`} style={{ height }} />;
}
