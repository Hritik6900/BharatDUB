"use client";
import { useEffect, useRef } from "react";

const HUES = ["--hi", "--bn", "--te", "--en", "--ta"];
type RGB = [number, number, number];

function rgb(hex: string): RGB {
  const m = hex.trim().match(/^#([0-9a-f]{6})$/i);
  if (!m) return [136, 136, 136];
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/**
 * Decoration behind the landing headline: a floor of dots seen in perspective, moving like sound. One voice sits under
 * the headline and its ripples travel out to every side; the floor runs through the language hues from left to right.
 * A second ripple follows the pointer. It is an illustration (no audio is read). Reduced motion: one still frame.
 */
export function VoiceField({ className = "" }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const cv = ref.current;
    const g = cv?.getContext("2d");
    if (!cv || !g) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let hues: RGB[] = [];
    let dark = false;
    const readTheme = () => {
      const cs = getComputedStyle(cv);
      hues = HUES.map((h) => rgb(cs.getPropertyValue(h)));
      dark = rgb(cs.getPropertyValue("--bg"))[0] < 128;
    };
    readTheme();
    const themeWatch = new MutationObserver(readTheme);
    themeWatch.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "class"] });

    const ptr = { x: -1, y: -1, on: 0 }; // canvas pixels; `on` eases 0..1
    const onMove = (e: PointerEvent) => {
      const r = cv.getBoundingClientRect();
      const inside = e.clientY >= r.top && e.clientY <= r.bottom;
      ptr.x = inside ? e.clientX - r.left : -1;
      ptr.y = inside ? e.clientY - r.top : -1;
    };
    window.addEventListener("pointermove", onMove, { passive: true });

    let visible = true;
    let raf = 0;
    const seen = new IntersectionObserver(([e]) => {
      visible = e.isIntersecting;
      if (visible && !reduced && !raf) raf = requestAnimationFrame(draw);
    });
    seen.observe(cv);

    const smooth = (a: number, b: number, x: number) => {
      const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
      return t * t * (3 - 2 * t);
    };

    function draw(ms: number) {
      raf = 0;
      if (!cv || !g) return;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const w = cv.clientWidth;
      const h = cv.clientHeight;
      if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
        cv.width = Math.round(w * dpr);
        cv.height = Math.round(h * dpr);
      }
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, w, h);
      const t = ms / 1000;
      const narrow = w < 640;
      const cols = narrow ? 46 : 104;
      const rows = narrow ? 30 : 40;
      const cx = w / 2;
      const y0 = h * (narrow ? 0.3 : 0.34); // the horizon, behind the headline
      const speech = 0.6 + 0.4 * Math.sin(t * 1.7) * Math.sin(t * 0.63 + 1); // loudness of the voice, 0.2..1
      ptr.on += ((ptr.x >= 0 ? 1 : 0) - ptr.on) * 0.06;

      // The voice itself: three soft lights on the horizon that swell as it speaks.
      g.globalCompositeOperation = dark ? "lighter" : "source-over";
      [-0.2, 0.02, 0.22].forEach((off, i) => {
        const c = hues[[0, 2, 3][i]];
        const r = Math.max(w * 0.2, 240) * (0.8 + 0.3 * speech + 0.06 * Math.sin(t * 0.9 + i * 2));
        const x = cx + off * Math.min(w, 1200) + Math.sin(t * 0.4 + i) * 30;
        const glow = g.createRadialGradient(x, y0, 0, x, y0, r);
        glow.addColorStop(0, `rgba(${c[0]},${c[1]},${c[2]},${dark ? 0.26 : 0.16})`);
        glow.addColorStop(1, `rgba(${c[0]},${c[1]},${c[2]},0)`);
        g.fillStyle = glow;
        g.fillRect(x - r, y0 - r, r * 2, r * 2);
      });

      // Where the pointer is on the floor (u across, d into the distance), if it is over it.
      const pd = ptr.y > y0 ? Math.pow((ptr.y - y0) / (h - y0), 1 / 1.8) : -1;
      const pu = pd >= 0 ? (ptr.x - cx) / (w * (0.5 + 0.9 * pd)) : 0;

      // Height of the floor at (u across, d into the distance): ripples leaving the voice (far centre), a slow swell
      // over the whole floor, and the pointer's own ripple.
      const height = (u: number, d: number) => {
        const dist = Math.hypot(u * 1.25, d * 1.6);
        let wave = Math.sin(dist * 13 - t * 2.4) * Math.exp(-dist * 0.8) * speech * 1.35 + 0.45 * Math.sin(u * 5.2 + t * 0.8) * Math.cos(d * 6.5 - t * 0.55);
        if (pd >= 0 && ptr.on > 0.01) {
          const q = Math.hypot((u - pu) * 1.25, (d - pd) * 1.6);
          wave += Math.sin(q * 22 - t * 5) * Math.exp(-q * 5) * 1.2 * ptr.on;
        }
        return wave;
      };
      const X = (u: number, d: number) => cx + u * w * (0.5 + 0.9 * d);
      const Y = (d: number, wave: number) => y0 + (h - y0) * Math.pow(d, 1.8) - (10 + 64 * d) * wave;

      // The floor's contour lines: one per row, in the language spectrum from left to right.
      const spectrum = g.createLinearGradient(0, 0, w, 0);
      hues.forEach((c, i) => spectrum.addColorStop(i / (hues.length - 1), `rgb(${c[0]},${c[1]},${c[2]})`));
      g.strokeStyle = spectrum;
      for (let r = 1; r < rows; r++) {
        const d = r / (rows - 1);
        g.beginPath();
        let started = false;
        for (let c = 0; c < cols; c++) {
          const u = (c / (cols - 1)) * 2 - 1;
          const sx = X(u, d);
          if (sx < -60 || sx > w + 60) continue;
          const sy = Y(d, height(u, d));
          if (started) g.lineTo(sx, sy);
          else g.moveTo(sx, sy);
          started = true;
        }
        g.lineWidth = 0.6 + 0.9 * d;
        g.globalAlpha = (0.07 + 0.3 * d) * (dark ? 1 : 0.8);
        g.stroke();
      }

      // The dots on those lines: larger and brighter on a crest, dimmer straight behind the text.
      for (let c = 0; c < cols; c++) {
        const u = (c / (cols - 1)) * 2 - 1; // -1 left .. 1 right
        const f = ((u + 1) / 2) * (hues.length - 1);
        const a = hues[Math.floor(f)];
        const b = hues[Math.min(hues.length - 1, Math.floor(f) + 1)];
        const k = f - Math.floor(f);
        g.fillStyle = `rgb(${Math.round(a[0] + (b[0] - a[0]) * k)},${Math.round(a[1] + (b[1] - a[1]) * k)},${Math.round(a[2] + (b[2] - a[2]) * k)})`;
        for (let r = 0; r < rows; r++) {
          const d = r / (rows - 1); // 0 far .. 1 near
          const sx = X(u, d);
          if (sx < -8 || sx > w + 8) continue;
          const wave = height(u, d);
          const sy = Y(d, wave);
          const crest = Math.min(1, Math.max(0, wave * 0.5 + 0.5));
          const clear = 0.5 + 0.5 * smooth(0.08, 0.36, Math.abs(sx - cx) / w);
          g.globalAlpha = Math.min(1, (0.22 + 0.78 * d) * (0.35 + 0.65 * crest) * clear * (dark ? 1.2 : 1));
          const size = 1.1 + 2.6 * d + 2.2 * crest * crest * d;
          if (size < 1.6) g.fillRect(sx, sy, size, size);
          else {
            g.beginPath();
            g.arc(sx, sy, size / 2, 0, 6.2832);
            g.fill();
          }
        }
      }
      g.globalAlpha = 1;
      g.globalCompositeOperation = "source-over";
      if (!reduced && visible) raf = requestAnimationFrame(draw);
    }
    raf = requestAnimationFrame(draw);
    const onResize = () => {
      if (reduced) requestAnimationFrame(draw);
    };
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
