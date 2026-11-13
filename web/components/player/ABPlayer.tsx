"use client";
import { useEffect, useRef, useState } from "react";
import { Tag } from "lucide-react";
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
    <div className="card card-lift p-2">
      <div className="overflow-hidden rounded-[18px] bg-black">
        <video
          ref={v}
          controls
          playsInline
          className="mx-auto block max-h-[66vh] w-full"
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
      <div className="px-3 pb-3 pt-4 sm:px-4">
        <div className="h-1 overflow-hidden rounded-chip bg-line" aria-hidden>
          <div className="h-full rounded-chip transition-colors duration-500" style={{ background: hue, width: `${v.current?.duration ? (t / v.current.duration) * 100 : 0}%` }} />
        </div>
        <p lang={caption ? lang(caption.code).short : undefined} className="mt-5 min-h-[3.2em] text-center font-indic text-xl font-medium leading-snug" aria-live="off">
          {caption?.text}
        </p>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <div role="tablist" aria-label="Audio" className="flex flex-wrap gap-2">
            {tracks.map((tr) => {
              const sel = tr.key === active;
              return (
                <button
                  key={tr.key}
                  role="tab"
                  aria-selected={sel}
                  onClick={() => onActive(tr.key)}
                  className={`inline-flex h-10 items-center gap-2 rounded-chip border px-4 text-[0.95rem] transition-colors ${sel ? "border-fg bg-fg text-on-fg" : "border-line bg-surface hover:border-fg"}`}
                >
                  <span className="size-2.5 rounded-full" style={{ background: tr.key === "src" ? "var(--hi)" : lang(tr.key).hue }} />
                  {tr.label}
                </button>
              );
            })}
          </div>
          <p className="flex items-center gap-1.5 text-xs text-muted">
            <Tag aria-hidden className="size-3.5" />
            AI-dubbed by Bharat Dub
          </p>
        </div>
      </div>
    </div>
  );
}
