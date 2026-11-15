"use client";
import { useEffect, useRef } from "react";

const HUES = ["--hi", "--bn", "--te", "--en", "--ta"];
// The five languages of the landing story, each in its own script, circling the voice.
const WORDS = ["हिन्दी", "বাংলা", "తెలుగు", "English", "தமிழ்"];
const TAU = Math.PI * 2;
type RGB = [number, number, number];

function rgb(hex: string): RGB {
  const m = hex.trim().match(/^#([0-9a-f]{6})$/i);
  if (!m) return [136, 136, 136];
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
const css = (c: RGB, a: number) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;

interface Mote {
  rho: number; // orbit radius, in orb radii
  tilt: number; // how flat the orbit looks
  spin: number; // rotation of the orbit's plane
  speed: number;
  phase: number;
  hue: number;
  size: number;
}

/**
 * Decoration behind the landing headline: one large living orb, the voice. Colours churn inside it, its edge trembles
 * and throws rings as it speaks, dust circles it, and the languages orbit it in their own scripts.
 * The middle is kept dark (light on a light page) so the headline over it stays readable.
 * It is an illustration (no audio is read). Reduced motion: one still frame.
 */
export function HeroOrb({ className = "", lift = 0 }: { className?: string; /** px the canvas reaches above the hero (under the header) */ lift?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const cv = ref.current;
    const g = cv?.getContext("2d");
    if (!cv || !g) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let hues: RGB[] = [];
    let bg: RGB = [11, 10, 15];
    let dark = true;
    let font = "sans-serif";
    const readTheme = () => {
      const cs = getComputedStyle(cv);
      hues = HUES.map((h) => rgb(cs.getPropertyValue(h)));
      bg = rgb(cs.getPropertyValue("--bg"));
      dark = bg[0] < 128;
      font = cs.fontFamily || "sans-serif";
    };
    readTheme();
    const themeWatch = new MutationObserver(readTheme);
    themeWatch.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "class"] });

    // Dust around the orb. A fixed pseudo-random set, so every visit looks the same.
    let seed = 7;
    const rnd = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;
    const motes: Mote[] = Array.from({ length: 150 }, () => ({
      rho: 1.08 + Math.pow(rnd(), 1.6) * 1.05,
      tilt: 0.16 + rnd() * 0.5,
      spin: (rnd() - 0.5) * 1.1,
      speed: (0.1 + rnd() * 0.3) * (rnd() < 0.5 ? 1 : -1),
      phase: rnd() * TAU,
      hue: Math.floor(rnd() * HUES.length),
      size: 0.8 + rnd() * 2,
    }));

    const ptr = { x: 0, y: 0, tx: 0, ty: 0 }; // -1..1 from the orb's centre, eased
    const onMove = (e: PointerEvent) => {
      const r = cv.getBoundingClientRect();
      ptr.tx = Math.max(-1, Math.min(1, ((e.clientX - r.left) / r.width - 0.5) * 2));
      ptr.ty = Math.max(-1, Math.min(1, ((e.clientY - r.top) / r.height - 0.4) * 2));
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
      ptr.x += (ptr.tx - ptr.x) * 0.05;
      ptr.y += (ptr.ty - ptr.y) * 0.05;
      const R = Math.min(narrow ? w * 0.46 : 310, (h - lift) * 0.4);
      const cx = w / 2 + ptr.x * 14;
      const cy = lift + (h - lift) * (narrow ? 0.29 : 0.385) + ptr.y * 10;
      // Loudness of the voice, 0.15..1: phrases with pauses between them.
      const speech = Math.max(0.15, 0.55 + 0.45 * Math.sin(t * 1.9) * Math.sin(t * 0.67 + 1) + 0.12 * Math.sin(t * 7.3));
      const add = dark ? "lighter" : "source-over";

      // The orb's trembling edge.
      const wob = 0.012 + 0.034 * speech;
      const edge = (th: number) => R * (1 + wob * (0.5 * Math.sin(3 * th + t * 1.1) + 0.3 * Math.sin(5 * th - t * 1.7) + 0.2 * Math.sin(2 * th + t * 0.6)));
      const outline = (scale = 1) => {
        g.beginPath();
        for (let i = 0; i <= 96; i++) {
          const th = (i / 96) * TAU;
          const r = edge(th) * scale;
          const x = cx + Math.cos(th) * r;
          const y = cy + Math.sin(th) * r;
          if (i) g.lineTo(x, y);
          else g.moveTo(x, y);
        }
        g.closePath();
      };
      const ringPaint = (turn: number) => {
        if (typeof g.createConicGradient !== "function") return css(hues[2], 1);
        const c = g.createConicGradient(turn, cx, cy);
        hues.forEach((hu, i) => c.addColorStop(i / hues.length, css(hu, 1)));
        c.addColorStop(1, css(hues[0], 1));
        return c;
      };

      // 1. Light thrown around the orb.
      g.globalCompositeOperation = add;
      for (let i = 0; i < 3; i++) {
        const a = t * 0.25 + (i * TAU) / 3;
        const x = cx + Math.cos(a) * R * 0.55;
        const y = cy + Math.sin(a) * R * 0.4;
        const r = R * (1.7 + 0.35 * speech);
        const glow = g.createRadialGradient(x, y, 0, x, y, r);
        const c = hues[[0, 2, 3][i]];
        glow.addColorStop(0, css(c, dark ? 0.2 : 0.13));
        glow.addColorStop(1, css(c, 0));
        g.fillStyle = glow;
        g.fillRect(x - r, y - r, r * 2, r * 2);
      }

      // 2. Dust and languages behind the orb are drawn first, the ones in front after it.
      const drawMotes = (front: boolean) => {
        for (const m of motes) {
          const a = m.phase + t * m.speed;
          const depth = Math.sin(a); // > 0 = in front
          if (depth > 0 !== front) continue;
          const ox = Math.cos(a) * m.rho * R;
          const oy = Math.sin(a) * m.rho * R * m.tilt;
          const x = cx + ox * Math.cos(m.spin) - oy * Math.sin(m.spin);
          const y = cy + ox * Math.sin(m.spin) + oy * Math.cos(m.spin);
          if (!front && Math.hypot(x - cx, y - cy) < R * 0.98) continue; // hidden by the orb
          const near = 0.5 + 0.5 * depth;
          g.globalAlpha = (0.25 + 0.6 * near) * (0.7 + 0.3 * Math.sin(t * 2 + m.phase * 5)) * (dark ? 1 : 0.8);
          g.fillStyle = css(hues[m.hue], 1);
          g.beginPath();
          g.arc(x, y, (m.size * (0.6 + 0.7 * near) * (narrow ? 0.8 : 1)) / 2 + 0.3, 0, TAU);
          g.fill();
        }
        g.globalAlpha = 1;
      };
      const drawWords = (front: boolean) => {
        g.textAlign = "center";
        g.textBaseline = "middle";
        if (narrow) return; // no room beside the orb on a phone
        WORDS.forEach((word, i) => {
          const a = t * 0.2 + (i * TAU) / WORDS.length;
          const depth = Math.sin(a);
          if (depth > 0 !== front) return;
          const ox = Math.cos(a) * R * 1.72;
          const oy = Math.sin(a) * R * 0.36;
          const x = cx + ox * Math.cos(-0.2) - oy * Math.sin(-0.2);
          const y = cy + ox * Math.sin(-0.2) + oy * Math.cos(-0.2);
          const near = 0.5 + 0.5 * depth;
          // Out of the way of the headline: a word shows at the sides and fades as it crosses the text.
          const clear = smooth(1.08, 1.3, Math.abs(x - cx) / R);
          const alpha = (0.3 + 0.7 * near) * clear;
          if (alpha < 0.02) return;
          const px = (narrow ? 13 : 17) * (0.8 + 0.4 * near);
          g.font = `500 ${px}px ${font}`;
          const tw = g.measureText(word).width;
          g.globalAlpha = alpha;
          // A small pill behind the word, so it reads as a label and not as stray text.
          g.fillStyle = css(bg, dark ? 0.55 : 0.7);
          g.beginPath();
          g.roundRect(x - tw / 2 - px * 1.25, y - px * 0.95, tw + px * 2.1, px * 1.9, px);
          g.fill();
          g.strokeStyle = css(hues[i], 0.7);
          g.lineWidth = 1;
          g.stroke();
          g.fillStyle = css(hues[i], 1);
          g.beginPath();
          g.arc(x - tw / 2 - px * 0.45, y, px * 0.2, 0, TAU);
          g.fill();
          g.fillStyle = dark ? "rgba(243,240,234,0.95)" : "rgba(23,21,28,0.9)";
          g.fillText(word, x + px * 0.25, y + px * 0.06);
        });
        g.globalAlpha = 1;
      };
      g.globalCompositeOperation = "source-over";
      drawMotes(false);
      drawWords(false);

      // 3. Rings of sound leaving the orb.
      g.globalCompositeOperation = add;
      g.strokeStyle = ringPaint(t * 0.3);
      for (let i = 0; i < 4; i++) {
        const p = (t * 0.28 + i / 4) % 1;
        g.globalAlpha = Math.pow(1 - p, 2) * (0.18 + 0.4 * speech);
        g.lineWidth = 1.6 - p;
        outline(1.03 + p * 0.95);
        g.stroke();
      }
      g.globalAlpha = 1;

      // 4. The body: colours churning inside the edge.
      g.save();
      outline();
      g.clip();
      g.globalCompositeOperation = "source-over";
      g.fillStyle = css(bg, 1);
      g.fillRect(cx - R * 1.2, cy - R * 1.2, R * 2.4, R * 2.4);
      g.globalCompositeOperation = add;
      for (let i = 0; i < 9; i++) {
        const c = hues[i % hues.length];
        const a = t * (0.22 + (i % 4) * 0.07) * (i % 2 ? 1 : -1) + i * 1.9;
        const reach = R * (0.38 + 0.2 * Math.sin(t * 0.5 + i));
        const x = cx + Math.cos(a) * reach - ptr.x * R * 0.12;
        const y = cy + Math.sin(a * 1.3) * reach - ptr.y * R * 0.12;
        const r = R * (0.62 + 0.22 * Math.sin(t * 0.8 + i * 2) + 0.14 * speech);
        const blob = g.createRadialGradient(x, y, 0, x, y, r);
        blob.addColorStop(0, css(c, dark ? 0.62 : 0.5));
        blob.addColorStop(1, css(c, 0));
        g.fillStyle = blob;
        g.fillRect(x - r, y - r, r * 2, r * 2);
      }
      // A veil over the middle keeps the headline readable and makes the orb look hollow, like glass.
      g.globalCompositeOperation = "source-over";
      const veil = g.createRadialGradient(cx, cy, 0, cx, cy, R);
      veil.addColorStop(0, css(bg, dark ? 0.78 : 0.72));
      veil.addColorStop(0.58, css(bg, dark ? 0.6 : 0.52));
      veil.addColorStop(0.86, css(bg, 0.16));
      veil.addColorStop(1, css(bg, 0));
      g.fillStyle = veil;
      g.fillRect(cx - R * 1.2, cy - R * 1.2, R * 2.4, R * 2.4);
      // A highlight high on the left, as on a glass ball.
      const shine = g.createRadialGradient(cx - R * 0.42, cy - R * 0.55, 0, cx - R * 0.42, cy - R * 0.55, R * 0.6);
      shine.addColorStop(0, `rgba(255,255,255,${dark ? 0.2 : 0.55})`);
      shine.addColorStop(1, "rgba(255,255,255,0)");
      g.fillStyle = shine;
      g.fillRect(cx - R * 1.2, cy - R * 1.2, R * 2.4, R * 2.4);
      g.restore();

      // 5. The glowing edge, its colours turning.
      g.globalCompositeOperation = add;
      g.strokeStyle = ringPaint(-t * 0.45);
      g.shadowColor = css(hues[Math.floor(t * 0.4) % hues.length], 0.9);
      g.shadowBlur = 26 + 30 * speech;
      g.lineWidth = 2.2 + 1.6 * speech;
      outline();
      g.stroke();
      g.shadowBlur = 0;
      g.lineWidth = 1;
      g.globalAlpha = 0.5;
      outline(0.965);
      g.stroke();
      g.globalAlpha = 1;

      g.globalCompositeOperation = "source-over";
      drawMotes(true);
      drawWords(true);
      if (!reduced && visible) raf = requestAnimationFrame(draw);
    }
    raf = requestAnimationFrame(draw);
    // Fonts for the scripts load after first paint; draw again once they are in (matters for the still frame).
    void document.fonts?.ready.then(() => {
      readTheme();
      if (reduced) requestAnimationFrame(draw);
    });
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
  }, [lift]);

  return <canvas ref={ref} aria-hidden className={`block size-full font-indic ${className}`} />;
}
