"use client";
import { useEffect, useRef } from "react";

interface Props {
  size?: number | string;
  /** 0..1 loudness, if the caller already measures it. */
  level?: number;
  /** Or hand over an analyser and the orb measures loudness itself. */
  analyser?: AnalyserNode | null;
  className?: string;
}

/** The voice orb: a slow spectrum of the language hues that swells with loudness. Breathes when idle. */
export function VoiceOrb({ size = 220, level, analyser = null, className = "" }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!analyser || !el) return;
    const buf = new Uint8Array(analyser.fftSize);
    let raf = 0;
    let smooth = 0;
    const tick = () => {
      analyser.getByteTimeDomainData(buf);
      let sum = 0;
      for (const v of buf) {
        const x = (v - 128) / 128;
        sum += x * x;
      }
      smooth = smooth * 0.8 + Math.min(1, Math.sqrt(sum / buf.length) * 5) * 0.2;
      el.style.setProperty("--lvl", smooth.toFixed(3));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      el.style.setProperty("--lvl", "0");
    };
  }, [analyser]);

  useEffect(() => {
    if (level !== undefined) ref.current?.style.setProperty("--lvl", Math.min(1, level).toFixed(3));
  }, [level]);

  const idle = !analyser && level === undefined;
  return (
    <div ref={ref} aria-hidden className={`orb ${idle ? "orb-idle" : ""} ${className}`} style={{ width: size }}>
      <span className="orb-glow" />
      <span className="orb-ring" />
      <span className="orb-core" />
      <span className="orb-shine" />
    </div>
  );
}
