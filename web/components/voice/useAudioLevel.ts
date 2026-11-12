"use client";
import { useEffect, useRef, useState } from "react";

/** AnalyserNode -> normalized amplitude (0..1) on rAF. Pass an AudioNode (mic or element source). */
export function useAudioLevel(node: AudioNode | null, ctx: AudioContext | null): number {
  const [level, setLevel] = useState(0);
  const raf = useRef(0);
  useEffect(() => {
    if (!node || !ctx) return;
    const an = ctx.createAnalyser();
    an.fftSize = 512;
    node.connect(an);
    const buf = new Float32Array(an.fftSize);
    let smooth = 0;
    const tick = () => {
      an.getFloatTimeDomainData(buf);
      let sum = 0;
      for (const v of buf) sum += v * v;
      const rms = Math.sqrt(sum / buf.length);
      smooth = smooth * 0.75 + Math.min(1, rms * 6) * 0.25;
      setLevel(smooth);
      raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf.current);
      try {
        node.disconnect(an);
      } catch {
        /* already gone */
      }
    };
  }, [node, ctx]);
  return level;
}
