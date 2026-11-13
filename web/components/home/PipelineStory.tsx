"use client";
import { useMemo, useRef } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";
import { AudioLines, Ear, Languages, ScanText, type LucideIcon } from "lucide-react";
import { Waveform, speechEnvelope } from "@/components/voice/Waveform";
import { useReducedMotion } from "@/lib/hooks";

gsap.registerPlugin(ScrollTrigger, useGSAP);

const STAGES: { title: string; text: string; icon: LucideIcon }[] = [
  { title: "Listen", text: "We lift your voice off the music and game sound, so the background survives the dub.", icon: Ear },
  { title: "Understand", text: "Prisma turns Hinglish speech into text, word by word, English slang included.", icon: ScanText },
  { title: "Translate", text: "The sentence is rebuilt in Tamil. Word order changes; words like chat and map stay.", icon: Languages },
  { title: "Speak", text: "Your voice says it in Tamil, timed to the same moment in the video.", icon: AudioLines },
];
const SRC = ["Chat", "mein", "batao,", "next", "kaunsa", "map", "khelein?"];
const DST = ["Chat-ல", "சொல்லுங்க,", "அடுத்து", "எந்த", "map", "விளையாடலாம்?"];
const KEEP = (w: string) => /^(chat|map)/i.test(w);
const word = "rounded-[12px] border bg-surface px-3 py-1.5 font-indic text-lg font-medium sm:text-xl";

function Visual({ stage }: { stage?: number }) {
  const voice = useMemo(() => speechEnvelope(90, 5), []);
  const noise = useMemo(() => speechEnvelope(160, 99).map((v) => 0.15 + v * 0.35), []);
  const show = (i: number) => (stage === undefined ? undefined : { opacity: stage === i ? 1 : 0 });
  return (
    <div className="card card-lift relative h-[320px] overflow-hidden sm:h-[380px]">
      <div data-v="0" className="absolute inset-0 grid place-items-center px-8" style={show(0)}>
        <div className="relative w-full">
          <div data-noise className="absolute inset-0 opacity-70">
            <Waveform samples={noise} hue="var(--muted)" height={160} strokeWidth={1.5} />
          </div>
          <Waveform samples={voice} hue="var(--hi)" height={160} />
          <p className="mt-4 text-center text-sm text-muted">Your voice, with the background behind it</p>
        </div>
      </div>
      <div data-v="1" className="absolute inset-0 flex flex-wrap content-center items-center justify-center gap-2 px-8" style={show(1)}>
        {SRC.map((w) => (
          <span key={w} data-word className={`${word} ${KEEP(w) ? "border-fg" : "border-[var(--hi)]"}`}>
            {w}
          </span>
        ))}
      </div>
      <div data-v="2" className="absolute inset-0 flex flex-col justify-center gap-6 px-8" style={show(2)}>
        <div className="flex flex-wrap gap-2 opacity-45">
          {SRC.map((w) => (
            <span key={w} className={`rounded-[10px] border px-2.5 py-1 ${KEEP(w) ? "border-fg" : "border-line"}`}>{w}</span>
          ))}
        </div>
        <div className="flex flex-wrap gap-2" lang="ta">
          {DST.map((w) => (
            <span key={w} data-tword className={`${word} ${KEEP(w) ? "border-fg" : "border-[var(--ta)]"}`}>
              {w}
            </span>
          ))}
        </div>
        <p className="text-sm text-muted">Outlined in ink: kept in English, in a new position.</p>
      </div>
      <div data-v="3" className="absolute inset-0 grid place-items-center px-8" style={show(3)}>
        <div className="w-full">
          <Waveform samples={voice} hue="var(--ta)" height={160} />
          <p className="mt-4 text-center font-accent text-3xl italic">your voice, in Tamil</p>
        </div>
      </div>
    </div>
  );
}

function Step({ i, title, text, icon: Icon }: { i: number; title: string; text: string; icon: LucideIcon }) {
  return (
    <li data-t={i} className="flex gap-4">
      <span className="grid size-11 shrink-0 place-items-center rounded-[14px] border border-line bg-surface">
        <Icon aria-hidden className="size-5" />
      </span>
      <div>
        <p className="text-lg font-medium tracking-[-0.01em]">
          <span className="tnum mr-2 font-mono text-sm text-muted">0{i + 1}</span>
          {title}
        </p>
        <p className="mt-1 max-w-[40ch] text-muted">{text}</p>
      </div>
    </li>
  );
}

const Heading = () => (
  <>
    <p className="eyebrow">How it works</p>
    <h2 id="story-h" className="h-display mt-4 text-[clamp(2.4rem,5vw,3.75rem)]">
      How a line <em>gets dubbed</em>
    </h2>
  </>
);

/** Scroll-pinned story: one line of speech goes through the four stages. Unpinned list for reduced motion. */
export function PipelineStory() {
  const root = useRef<HTMLElement>(null);
  const reduced = useReducedMotion();

  useGSAP(
    () => {
      if (reduced) return;
      const v = (i: number) => `[data-v="${i}"]`;
      const t = (i: number) => `[data-t="${i}"]`;
      gsap.set([v(1), v(2), v(3)], { autoAlpha: 0 });
      gsap.set([t(1), t(2), t(3)], { opacity: 0.35 });
      const tl = gsap.timeline({
        defaults: { ease: "none" },
        scrollTrigger: { trigger: root.current, start: "top top", end: "+=300%", scrub: true, pin: true, refreshPriority: 1 },
      });
      tl.to("[data-noise]", { autoAlpha: 0, duration: 1 })
        .to("[data-progress]", { scaleX: 0.25, duration: 1 }, 0)
        .to(v(0), { autoAlpha: 0, duration: 0.3 })
        .to(v(1), { autoAlpha: 1, duration: 0.3 }, "<")
        .to(t(0), { opacity: 0.35, duration: 0.3 }, "<")
        .to(t(1), { opacity: 1, duration: 0.3 }, "<")
        .from("[data-word]", { y: 16, autoAlpha: 0, stagger: 0.1, duration: 0.5 })
        .to("[data-progress]", { scaleX: 0.5, duration: 1 }, "<")
        .to(v(1), { autoAlpha: 0, duration: 0.3 })
        .to(v(2), { autoAlpha: 1, duration: 0.3 }, "<")
        .to(t(1), { opacity: 0.35, duration: 0.3 }, "<")
        .to(t(2), { opacity: 1, duration: 0.3 }, "<")
        .from("[data-tword]", { x: -24, autoAlpha: 0, stagger: 0.12, duration: 0.5 })
        .to("[data-progress]", { scaleX: 0.75, duration: 1 }, "<")
        .to(v(2), { autoAlpha: 0, duration: 0.3 })
        .to(v(3), { autoAlpha: 1, duration: 0.3 }, "<")
        .to(t(2), { opacity: 0.35, duration: 0.3 }, "<")
        .to(t(3), { opacity: 1, duration: 0.3 }, "<")
        .to("[data-progress]", { scaleX: 1, duration: 1 });
    },
    { scope: root, dependencies: [reduced], revertOnUpdate: true },
  );

  if (reduced) {
    return (
      <section id="how" aria-labelledby="story-h" className="mx-auto max-w-6xl px-5 py-24 sm:px-8">
        <Heading />
        <ol className="mt-12 grid gap-10">
          {STAGES.map((s, i) => (
            <li key={s.title} className="grid gap-6 md:grid-cols-[1fr_1.4fr] md:items-center">
              <ol>
                <Step i={i} {...s} />
              </ol>
              <Visual stage={i} />
            </li>
          ))}
        </ol>
      </section>
    );
  }

  return (
    <section id="how" ref={root} aria-labelledby="story-h" className="flex min-h-svh items-center bg-sunken/60">
      <div className="mx-auto grid w-full max-w-6xl gap-10 px-5 py-24 sm:px-8 md:grid-cols-[1fr_1.3fr] md:items-center">
        <div>
          <Heading />
          <div className="mt-7 h-[3px] overflow-hidden rounded-chip bg-line" aria-hidden>
            <div data-progress className="spectrum h-full origin-left scale-x-0 rounded-chip" />
          </div>
          <ol className="mt-8 space-y-6">
            {STAGES.map((s, i) => (
              <Step key={s.title} i={i} {...s} />
            ))}
          </ol>
        </div>
        <Visual />
      </div>
    </section>
  );
}
