"use client";
import { useState } from "react";
import { Captions, Languages, Mic } from "lucide-react";
import { VoiceBars } from "@/components/voice/VoiceBars";
import { LANGS, SHOWCASE_LANGS as TARGET_LANGS } from "@/lib/langs";

/** One reel, with and without a dub. Counts are the product's own: 1 language in, 5 out, 4 subtitle files. */
export function BeforeAfter() {
  const [after, setAfter] = useState(true);
  const rows = [
    {
      icon: Languages,
      title: "Languages",
      tag: after ? `${LANGS.length} languages` : "1 language",
      text: after ? "Hindi, plus Tamil, Bengali, Telugu and English." : "Hindi only. Everyone else scrolls past.",
      visual: (
        <span className="flex gap-1.5">
          {LANGS.map((l, i) => (
            <span key={l.code} className="h-8 w-6 rounded-[5px] transition-colors duration-500" style={{ background: after || i === 0 ? l.hue : "var(--line)" }} />
          ))}
        </span>
      ),
    },
    {
      icon: Mic,
      title: "Voice",
      tag: after ? "Still you" : "You",
      text: after ? "The same voice, speaking every one of them." : "Your voice, in the one language you recorded.",
      visual: <VoiceBars key={String(after)} colors={after ? ["--hi", "--bn", "--te", "--en", "--ta"] : ["--hi"]} bars={22} height={32} className="!w-[168px]" />,
    },
    {
      icon: Captions,
      title: "Subtitles",
      tag: after ? `${TARGET_LANGS.length} files` : "0 files",
      text: after ? "A timed subtitle file for each dubbed language." : "None, unless you type them out yourself.",
      visual: (
        <span className="flex gap-1.5">
          {TARGET_LANGS.map((l) => (
            <span key={l.code} className={`grid h-8 w-10 place-items-center rounded-[5px] font-mono text-[10px] transition-colors duration-500 ${after ? "bg-fg text-on-fg" : "bg-line text-transparent"}`}>
              SRT
            </span>
          ))}
        </span>
      ),
    },
  ];
  return (
    <section aria-labelledby="ba-h" className="px-3 sm:px-5">
      <div data-reveal className="tex-tint mx-auto grid max-w-6xl grid-cols-1 gap-10 rounded-[32px] border border-line p-6 sm:p-12 lg:grid-cols-[1fr_1.25fr] lg:items-stretch">
        <div className="flex flex-col">
          <h2 id="ba-h" className="h-display text-[clamp(2.2rem,4.6vw,3.4rem)]">
            The same reel, <em>before and after</em>
          </h2>
          <p className="mt-4 max-w-[38ch] text-[1.05rem] text-muted">Same video, same creator, same minute of work.</p>
          <div role="radiogroup" aria-label="Show" className="relative mt-10 grid w-56 grid-cols-2 rounded-chip border border-line bg-surface p-1 lg:mt-auto">
            <span aria-hidden className="absolute inset-y-1 left-1 w-[calc(50%-0.25rem)] rounded-chip bg-fg transition-transform duration-300" style={{ transform: after ? "translateX(100%)" : "none" }} />
            {["Before", "After"].map((label, i) => {
              const on = (i === 1) === after;
              return (
                <button key={label} type="button" role="radio" aria-checked={on} onClick={() => setAfter(i === 1)} className={`relative h-11 rounded-chip font-medium transition-colors ${on ? "text-on-fg" : "text-muted"}`}>
                  {label}
                </button>
              );
            })}
          </div>
        </div>
        <ul className="card card-lift divide-y divide-line overflow-hidden" aria-live="polite">
          {rows.map((r) => (
            <li key={r.title} className="flex flex-wrap items-center gap-x-5 gap-y-4 p-5 sm:p-6">
              <span className="grid size-11 shrink-0 place-items-center rounded-[14px] border border-line bg-bg">
                <r.icon aria-hidden className="size-5" />
              </span>
              <div className="min-w-[12rem] flex-1">
                <p className="font-medium">{r.title}</p>
                <p className="text-muted">{r.text}</p>
              </div>
              <div className="flex flex-col items-end gap-2">
                <span className="eyebrow">{r.tag}</span>
                {r.visual}
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
