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
const css = (c: RGB, a = 1) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;

/**
 * Decoration behind the landing hero: a floor of dots seen in perspective, moving like sound. One voice sits on the
 * horizon behind the headline. Its ripples travel out over the floor, and with every "phrase" a bright ring sweeps
 * outwards and lights the dots it passes. Crests throw up beams like the bars of a level meter, sparks rise from the
 * floor, and the floor runs through the language hues from left to right. The pointer makes a ripple of its own.
 * It is an illustration (no audio is read). Reduced motion: one still frame.
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

    // Sparks: a fixed pseudo-random set, so every visit looks the same.
    let seed = 5;
    const rnd = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;
    const sparks = Array.from({ length: 70 }, () => ({ u: rnd() * 2 - 1, d: 0.15 + rnd() * 0.85, speed: 0.05 + rnd() * 0.09, phase: rnd(), size: 0.8 + rnd() * 1.6 }));

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
      const k = Math.min(1, Math.max(0, (x - a) / (b - a)));
      return k * k * (3 - 2 * k);
    };
    const PULSE_S = 2.6; // one bright ring leaves the voice this often

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
      const t = reduced ? 1.3 : ms / 1000;
      const narrow = w < 640;
      const cols = narrow ? 54 : 116;
      const rows = narrow ? 34 : 42;
      const cx = w / 2;
      const y0 = h * (narrow ? 0.3 : 0.34); // the horizon, behind the headline
      const speech = 0.62 + 0.38 * Math.sin(t * 1.7) * Math.sin(t * 0.63 + 1); // loudness of the voice
      const ring = ((t / PULSE_S) % 1) * 2.4; // how far the bright ring has travelled over the floor
      const ringFade = 1 - (t / PULSE_S) % 1;
      ptr.on += ((ptr.x >= 0 ? 1 : 0) - ptr.on) * 0.06;
      const add = dark ? "lighter" : "source-over";

      // The voice: lights on the horizon that swell as it speaks, and flash as a ring leaves.
      g.globalCompositeOperation = add;
      const flash = Math.pow(ringFade, 6);
      [-0.24, 0, 0.24].forEach((off, i) => {
        const c = hues[[0, 2, 3][i]];
        const r = Math.max(w * 0.22, 250) * (0.85 + 0.3 * speech + 0.25 * flash);
        const x = cx + off * Math.min(w, 1200) + Math.sin(t * 0.4 + i) * 30;
        const glow = g.createRadialGradient(x, y0, 0, x, y0, r);
        glow.addColorStop(0, css(c, (dark ? 0.3 : 0.17) + 0.1 * flash));
        glow.addColorStop(1, css(c, 0));
        g.fillStyle = glow;
        g.fillRect(x - r, y0 - r, r * 2, r * 2);
      });

      // Where the pointer is on the floor (u across, d into the distance), if it is over it.
      const pd = ptr.y > y0 ? Math.pow((ptr.y - y0) / (h - y0), 1 / 1.8) : -1;
      const pu = pd >= 0 ? (ptr.x - cx) / (w * (0.5 + 0.9 * pd)) : 0;

      // Height of the floor at (u, d), and how strongly the bright ring is passing there.
      let lit = 0;
      const height = (u: number, d: number) => {
        const dist = Math.hypot(u * 1.25, d * 1.6);
        const k = (dist - ring) / 0.11;
        lit = Math.exp(-k * k) * ringFade;
        let wave = Math.sin(dist * 13 - t * 2.4) * Math.exp(-dist * 0.75) * speech * 1.4 + 0.5 * Math.sin(u * 5.2 + t * 0.8) * Math.cos(d * 6.5 - t * 0.55) + lit * 0.95;
        if (pd >= 0 && ptr.on > 0.01) {
          const q = Math.hypot((u - pu) * 1.25, (d - pd) * 1.6);
          wave += Math.sin(q * 22 - t * 5) * Math.exp(-q * 4.5) * 1.3 * ptr.on;
        }
        return wave;
      };
      const X = (u: number, d: number) => cx + u * w * (0.5 + 0.9 * d);
      const floorY = (d: number) => y0 + (h - y0) * Math.pow(d, 1.8);
      const lift = (d: number) => (narrow ? 8 + 44 * d : 12 + 84 * d);

      // Every grid point's height and ring glow, worked out once per frame and used by the lines and the dots.
      const H = new Float32Array(cols * rows);
      const L = new Float32Array(cols * rows);
      for (let c = 0; c < cols; c++) {
        const u = (c / (cols - 1)) * 2 - 1;
        for (let r = 0; r < rows; r++) {
          H[c * rows + r] = height(u, r / (rows - 1));
          L[c * rows + r] = lit;
        }
      }
      const spectrum = g.createLinearGradient(0, 0, w, 0);
      hues.forEach((c, i) => spectrum.addColorStop(i / (hues.length - 1), css(c)));

      // The horizon: a thin line of light the floor starts from.
      const horizon = g.createLinearGradient(0, 0, w, 0);
      horizon.addColorStop(0, css(hues[0], 0));
      hues.forEach((c, i) => horizon.addColorStop(0.15 + (i / (hues.length - 1)) * 0.7, css(c, (dark ? 0.75 : 0.5) * (0.6 + 0.4 * speech))));
      horizon.addColorStop(1, css(hues[4], 0));
      g.fillStyle = horizon;
      g.fillRect(0, y0 - 0.75, w, 1.5);

      // The floor's contour lines, one per row.
      g.strokeStyle = spectrum;
      for (let r = 1; r < rows; r++) {
        const d = r / (rows - 1);
        g.beginPath();
        let started = false;
        for (let c = 0; c < cols; c += 2) {
          const u = (c / (cols - 1)) * 2 - 1;
          const sx = X(u, d);
          if (sx < -80 || sx > w + 80) continue;
          const sy = floorY(d) - lift(d) * H[c * rows + r];
          if (started) g.lineTo(sx, sy);
          else g.moveTo(sx, sy);
          started = true;
        }
        g.lineWidth = 0.6 + 1.1 * d;
        g.globalAlpha = (0.09 + 0.34 * d) * (dark ? 1 : 0.8);
        g.stroke();
      }

      // Dots, and the beams that crests throw up from the floor.
      for (let c = 0; c < cols; c++) {
        const u = (c / (cols - 1)) * 2 - 1; // -1 left .. 1 right
        const f = ((u + 1) / 2) * (hues.length - 1);
        const a = hues[Math.floor(f)];
        const b = hues[Math.min(hues.length - 1, Math.floor(f) + 1)];
        const k = f - Math.floor(f);
        const col: RGB = [Math.round(a[0] + (b[0] - a[0]) * k), Math.round(a[1] + (b[1] - a[1]) * k), Math.round(a[2] + (b[2] - a[2]) * k)];
        const own = css(col);
        g.fillStyle = own;
        for (let r = 0; r < rows; r++) {
          const d = r / (rows - 1); // 0 far .. 1 near
          const sx = X(u, d);
          if (sx < -8 || sx > w + 8) continue;
          const wave = H[c * rows + r];
          const hot = L[c * rows + r]; // 0..1, the bright ring passing this dot
          const sy = floorY(d) - lift(d) * wave;
          const crest = Math.min(1, Math.max(0, wave * 0.5 + 0.5));
          // Dimmer straight behind the text, so the words always win.
          const clear = 0.5 + 0.5 * smooth(0.08, 0.36, Math.abs(sx - cx) / w);
          const alpha = Math.min(1, ((0.24 + 0.76 * d) * (0.35 + 0.65 * crest) + hot * 0.8) * clear * (dark ? 1.2 : 1));
          // A beam under a high crest, like one bar of a level meter standing on the floor.
          if (wave > 0.55 && d > 0.12 && c % 2 === 0) {
            const top = sy;
            const bottom = floorY(d);
            const strength = Math.min(1, (wave - 0.55) * 1.6) * (0.25 + 0.6 * d) * clear;
            const mid = top + (bottom - top) * 0.45;
            g.globalAlpha = strength * 0.6;
            g.fillRect(sx - (0.5 + d), top, 1 + 2 * d, mid - top);
            g.globalAlpha = strength * 0.22;
            g.fillRect(sx - (0.5 + d), mid, 1 + 2 * d, bottom - mid);
          }
          g.globalAlpha = alpha;
          if (hot > 0.12) {
            // White-hot while the ring passes.
            const m = Math.min(1, hot * (dark ? 0.85 : 0.35));
            g.fillStyle = css([Math.round(col[0] + (255 - col[0]) * m), Math.round(col[1] + (255 - col[1]) * m), Math.round(col[2] + (255 - col[2]) * m)]);
          }
          const size = 1.1 + 2.7 * d + 2.4 * crest * crest * d + hot * (1.5 + 3 * d);
          if (size < 1.6) g.fillRect(sx, sy, size, size);
          else {
            g.beginPath();
            g.arc(sx, sy, size / 2, 0, 6.2832);
            g.fill();
          }
          if (hot > 0.12) g.fillStyle = own;
        }
      }

      // Sparks rising off the floor.
      for (const s of sparks) {
        const life = (t * s.speed + s.phase) % 1; // 0 leaving the floor .. 1 gone
        const sx = X(s.u, s.d) + Math.sin(t * 0.9 + s.phase * 20) * 8;
        if (sx < 0 || sx > w) continue;
        const sy = floorY(s.d) - life * (60 + 220 * s.d);
        const f = ((s.u + 1) / 2) * (hues.length - 1);
        g.fillStyle = css(hues[Math.round(f)]);
        g.globalAlpha = Math.sin(life * Math.PI) * (0.3 + 0.6 * s.d) * (0.5 + 0.5 * smooth(0.08, 0.36, Math.abs(sx - cx) / w)) * (dark ? 1 : 0.7);
        g.beginPath();
        g.arc(sx, sy, (s.size * (0.5 + s.d)) / 2 + 0.4, 0, 6.2832);
        g.fill();
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
