"use client";
import { useEffect, useRef, useState } from "react";
import type { Segment } from "@/lib/api";
import { lang } from "@/lib/langs";

export interface Track {
  key: string; // "src" or lang code
  label: string;
  url: string;
}

interface Props {
  tracks: Track[];
  active: string;
  onActive: (k: string) => void;
  segments: Segment[];
  seekTo?: { t: number; n: number } | null;
}

/** One video element; switching track keeps currentTime and play state. Captions from segments. */
export function ABPlayer({ tracks, active, onActive, segments, seekTo }: Props) {
  const v = useRef<HTMLVideoElement>(null);
  const [t, setT] = useState(0);
  const pending = useRef<{ time: number; play: boolean } | null>(null);
  const track = tracks.find((x) => x.key === active) ?? tracks[0];

  useEffect(() => {
    const el = v.current;
    if (!el || !track) return;
    if (el.src && el.currentSrc) pending.current = { time: el.currentTime, play: !el.paused };
    el.src = track.url;
    el.load();
  }, [track?.url]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!seekTo || !v.current) return;
    v.current.currentTime = seekTo.t;
    void v.current.play().catch(() => {});
  }, [seekTo]);

  const caption = (() => {
    const s = segments.find((x) => x.start_s <= t && t < x.end_s + 0.4);
    if (!s) return null;
    if (active === "src") return { text: s.src_text, code: "hi-IN" };
    const tr = s.translations.find((x) => x.lang === active);
    return tr ? { text: tr.text, code: active } : null;
  })();
  const hue = active === "src" ? "var(--hi)" : lang(active).hue;

  return (
    <div>
      <div className="overflow-hidden rounded-media bg-black shadow-[0_20px_60px_-30px_rgba(20,22,31,.35)]">
        <video
          ref={v}
          controls
          playsInline
          className="mx-auto block max-h-[70vh] w-full"
          onTimeUpdate={(e) => setT(e.currentTarget.currentTime)}
          onLoadedMetadata={(e) => {
            const p = pending.current;
            if (p) {
              e.currentTarget.currentTime = p.time;
              if (p.play) void e.currentTarget.play().catch(() => {});
              pending.current = null;
            }
          }}
        />
      </div>
      <div className="mt-3 h-1 overflow-hidden rounded-chip bg-mist" aria-hidden>
        <div className="voice-ribbon h-full" style={{ ["--to" as string]: hue, width: `${v.current?.duration ? (t / v.current.duration) * 100 : 0}%` }} />
      </div>
      <p lang={caption ? lang(caption.code).short : undefined} className="mt-4 min-h-[3.2em] text-center font-display text-xl leading-snug" aria-live="off">
        {caption && <span className="border-b-2 pb-0.5" style={{ borderColor: hue }}>{caption.text}</span>}
      </p>
      <div role="tablist" aria-label="Audio" className="mt-4 flex flex-wrap justify-center gap-2">
        {tracks.map((tr) => {
          const sel = tr.key === active;
          const h = tr.key === "src" ? "var(--hi)" : lang(tr.key).hue;
          return (
            <button
              key={tr.key}
              role="tab"
              aria-selected={sel}
              onClick={() => onActive(tr.key)}
              style={{ ["--hue" as string]: h }}
              className={`inline-flex h-11 items-center gap-2 rounded-chip border px-5 font-display ${sel ? "border-[var(--hue)] bg-[var(--hue)] text-white" : "border-mist bg-surface hover:border-[var(--hue)]"}`}
            >
              <span className={`size-2.5 rounded-full ${sel ? "bg-white" : "bg-[var(--hue)]"}`} />
              {tr.label}
            </button>
          );
        })}
      </div>
      <p className="mt-3 text-center text-xs text-slate">AI-dubbed by Bharat Dub</p>
    </div>
  );
}
