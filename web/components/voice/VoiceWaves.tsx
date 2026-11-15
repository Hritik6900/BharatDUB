"use client";
import { useEffect, useRef } from "react";

const HUES = ["--hi", "--bn", "--te", "--en", "--ta"];

/**
 * Decoration behind the landing headline: one voice as five ribbons, one per language hue, flowing across the page.
 * They run calm behind the text and open up towards the sides, and swell a little near the pointer.
 * It is an illustration (no audio is read). Reduced motion: one still frame.
 */
export function VoiceWaves({ className = "" }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const cv = ref.current;
    const g = cv?.getContext("2d");
    if (!cv || !g) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let colors: string[] = [];
    let dark = false;
    const readTheme = () => {
      const cs = getComputedStyle(cv);
      colors = HUES.map((h) => cs.getPropertyValue(h).trim() || "#888");
      // The page background decides how the ribbons are blended: glowing on dark, ink-like on light.
      const m = cs.getPropertyValue("--bg").trim().match(/^#([0-9a-f]{2})/i);
      dark = m ? parseInt(m[1], 16) < 128 : false;
    };
    readTheme();
    const themeWatch = new MutationObserver(readTheme);
    themeWatch.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "class"] });

    let pointer = -1; // 0..1 across the canvas, -1 = away
    let swell = 0;
    const onMove = (e: PointerEvent) => {
      const r = cv.getBoundingClientRect();
      pointer = e.clientY >= r.top && e.clientY <= r.bottom ? (e.clientX - r.left) / r.width : -1;
    };
    window.addEventListener("pointermove", onMove, { passive: true });

    let visible = true;
    const seen = new IntersectionObserver(([e]) => {
      visible = e.isIntersecting;
      if (visible && !reduced && !raf) raf = requestAnimationFrame(draw);
    });
    seen.observe(cv);

    let raf = 0;
    const draw = (ms: number) => {
      raf = 0;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const w = cv.clientWidth;
      const h = cv.clientHeight;
      if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
        cv.width = Math.round(w * dpr);
        cv.height = Math.round(h * dpr);
      }
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, w, h);
      g.globalCompositeOperation = dark ? "lighter" : "source-over";
      const t = ms / 1000;
      // On a phone the text fills the width, so the ribbons sit behind the headline only and stay small.
      const narrow = w < 640;
      const base = h * (narrow ? 0.42 : 0.56);
      const amp = narrow ? 58 : Math.min(h * 0.3, 150);
      const step = Math.max(6, w / 180);
      swell += ((pointer >= 0 ? 1 : 0) - swell) * 0.05;

      // How open the ribbons are at x (0..1): calm behind the headline, wide at the sides, a bump near the pointer.
      const open = (x: number) => {
        const side = Math.abs(x - 0.5) * 2;
        const calm = 0.2 + 0.8 * side * side * (3 - 2 * side);
        const near = pointer >= 0 ? Math.exp(-Math.pow((x - pointer) / 0.09, 2)) * 0.5 * swell : 0;
        return calm + near;
      };

      // Fine ticks along the centre line, like a level meter running the width of the page.
      g.fillStyle = colors[0];
      for (let x = 0, i = 0; x <= w; x += step * 1.6, i++) {
        const u = x / w;
        const talk = 0.5 + 0.5 * Math.sin(t * 2.1 + i * 0.7) * Math.cos(t * 1.3 - i * 0.23);
        const th = 3 + open(u) * amp * 0.34 * talk;
        g.globalAlpha = dark ? 0.16 : 0.13;
        g.fillStyle = colors[i % colors.length];
        g.fillRect(x, base - th / 2, 1.5, th);
      }

      colors.forEach((c, i) => {
        const phase = i * 1.37;
        const k1 = (1.6 + i * 0.22) * Math.PI * 2;
        const k2 = (3.1 + i * 0.35) * Math.PI * 2;
        const breath = 0.72 + 0.28 * Math.sin(t * 0.6 + phase);
        const y = (u: number) =>
          base + amp * open(u) * breath * (0.62 * Math.sin(k1 * u - t * (0.55 + i * 0.06) + phase) + 0.38 * Math.sin(k2 * u + t * (0.38 + i * 0.05) + phase * 2));
        g.beginPath();
        g.moveTo(0, y(0));
        for (let x = step; x <= w + step; x += step) g.lineTo(x, y(x / w));
        g.strokeStyle = c;
        g.lineWidth = 1.6;
        g.globalAlpha = dark ? 0.62 : 0.5;
        g.stroke();
        // A soft body under each line, so the ribbons read as sound rather than wires.
        g.lineTo(w, base);
        g.lineTo(0, base);
        g.closePath();
        g.fillStyle = c;
        g.globalAlpha = dark ? 0.07 : 0.055;
        g.fill();
      });
      g.globalAlpha = 1;
      if (!reduced && visible) raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    const onResize = () => reduced && requestAnimationFrame(draw);
    window.addEventListener("resize", onResize);
    return () => {
      cancelAnimationFrame(raf);
      themeWatch.disconnect();
      seen.disconnect();
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("resize", onResize);
    };
  }, []);

  return <canvas ref={ref} aria-hidden className={`block size-full ${className}`} />;
}
