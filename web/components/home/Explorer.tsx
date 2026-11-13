"use client";
import { useState } from "react";
import { ArrowRight, AudioLines, BookA, Captions, Clapperboard, Columns2, Gauge, MessagesSquare, Mic, MonitorPlay, Music2, PencilLine, Subtitles, type LucideIcon } from "lucide-react";
import { LinkButton } from "@/components/ui/Button";

interface Item {
  key: string;
  label: string;
  icon: LucideIcon;
  text: string;
}
interface Group {
  name: string;
  hue: string;
  title: string;
  lede: string;
  href: string;
  cta: string;
  items: Item[];
}

const GROUPS: Group[] = [
  {
    name: "Studio",
    hue: "var(--hi)",
    title: "Dub a finished video",
    lede: "Everything that happens to a reel between upload and download.",
    href: "/studio",
    cta: "Open Studio",
    items: [
      { key: "reels", label: "Reels and Shorts", icon: Clapperboard, text: "Upload a video up to 3 minutes. One dubbed MP4 comes back per language." },
      { key: "music", label: "Music kept", icon: Music2, text: "Your voice is separated from the background, then the dub is mixed back over it." },
      { key: "editor", label: "Line editor", icon: PencilLine, text: "Fix any translated line. Only that line is re-voiced and the video re-rendered." },
      { key: "ab", label: "A/B player", icon: Columns2, text: "Switch between the original and each dub on one timeline without losing your place." },
    ],
  },
  {
    name: "Live",
    hue: "var(--bn)",
    title: "Dub a stream as it happens",
    lede: "What your viewers get while you are still talking.",
    href: "/live",
    cta: "Open Live",
    items: [
      { key: "audio", label: "Dubbed audio", icon: AudioLines, text: "Viewers hear you in their language, a few seconds behind the stream." },
      { key: "captions", label: "Live captions", icon: Captions, text: "Each sentence appears as text as soon as it is translated, before the audio." },
      { key: "chat", label: "Viewer chat", icon: MessagesSquare, text: "Viewers write in their language. You read it translated into yours." },
      { key: "obs", label: "OBS overlay", icon: MonitorPlay, text: "A browser source that shows the translated chat on your stream." },
    ],
  },
  {
    name: "Shared",
    hue: "var(--te)",
    title: "One voice across both",
    lede: "Set these up once. Studio and Live both use them.",
    href: "/voices",
    cta: "Set up your voice",
    items: [
      { key: "voice", label: "Voice profile", icon: Mic, text: "Recorded once with spoken consent, used by Studio and Live. Deletable any time." },
      { key: "glossary", label: "Glossary", icon: BookA, text: "Names, game titles and catchphrases that are never translated." },
      { key: "subs", label: "Subtitles", icon: Subtitles, text: "A subtitle file for every language, timed to the dubbed lines." },
      { key: "numbers", label: "Measured numbers", icon: Gauge, text: "Turnaround and delay are recorded for every job and stream, and shown as they are." },
    ],
  },
];

/** Pick any capability; the panel below shows its product with that row lit. */
export function Explorer() {
  const [active, setActive] = useState("reels");
  const group = GROUPS.find((g) => g.items.some((i) => i.key === active)) ?? GROUPS[0];
  return (
    <section aria-labelledby="explore-h" className="px-3 sm:px-5">
      <div data-reveal className="tex-tint mx-auto max-w-[84rem] rounded-[32px] border border-line px-5 py-14 sm:px-10 sm:py-20">
        <div className="mx-auto max-w-6xl">
          <div className="flex flex-wrap items-end justify-between gap-6">
            <div>
              <p className="eyebrow">Everything it does</p>
              <h2 id="explore-h" className="h-display mt-4 text-[clamp(2.2rem,4.6vw,3.5rem)]">
                Twelve things, <em>one voice</em>
              </h2>
              <p className="mt-4 max-w-[52ch] text-[1.05rem] text-muted">Tap any of them to see where it sits.</p>
            </div>
            <LinkButton href={group.href}>
              {group.cta}
              <ArrowRight aria-hidden className="size-4 transition-transform group-hover:translate-x-0.5" />
            </LinkButton>
          </div>

          <div className="mt-12 grid grid-cols-1 gap-8 lg:grid-cols-3">
            {GROUPS.map((g) => (
              <div key={g.name}>
                <p className="flex items-center gap-2.5 font-medium">
                  <span aria-hidden className="size-2 rounded-full" style={{ background: g.hue }} />
                  {g.name}
                </p>
                <div role="group" aria-label={g.name} className="cells mt-4 grid-cols-2">
                  {g.items.map((i) => {
                    const on = i.key === active;
                    return (
                      <button
                        key={i.key}
                        type="button"
                        aria-pressed={on}
                        onClick={() => setActive(i.key)}
                        className="h-[3.25rem] px-2 text-[0.95rem] transition-colors hover:!bg-sunken"
                        style={on ? { background: `color-mix(in oklab, ${g.hue} 16%, var(--surface))` } : undefined}
                      >
                        {i.label}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>

          <div className="card card-lift mt-10 p-5 sm:p-8" aria-live="polite">
            <div key={group.name} className="rise">
              <h3 className="h-display text-[1.75rem] sm:text-[2rem]">{group.title}</h3>
              <p className="mt-2 text-muted">{group.lede}</p>
              <ul className="cells mt-7 sm:grid-cols-2">
                {group.items.map((i) => {
                  const on = i.key === active;
                  return (
                    <li key={i.key} className="relative flex gap-4 p-5 transition-colors sm:p-6" style={on ? { background: `color-mix(in oklab, ${group.hue} 9%, var(--surface))` } : undefined}>
                      {on && <span aria-hidden className="absolute inset-y-0 left-0 w-[3px]" style={{ background: group.hue }} />}
                      <i.icon aria-hidden className="mt-0.5 size-5 shrink-0" style={on ? { color: group.hue } : undefined} />
                      <div>
                        <p className="font-medium">{i.label}</p>
                        <p className="mt-1 text-muted">{i.text}</p>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
