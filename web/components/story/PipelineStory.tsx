"use client";
import { useMemo, useRef } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";
import { Waveform, speechEnvelope } from "@/components/voice/Waveform";
import { useReducedMotion } from "@/lib/hooks";

gsap.registerPlugin(ScrollTrigger, useGSAP);

const STAGES = [
  { title: "Listen", text: "We pull your voice apart from the music and game sound, so the background survives the dub." },
  { title: "Understand", text: "Prisma turns Hinglish speech into text, word by word, English slang included." },
  { title: "Translate", text: "The sentence is rebuilt in Tamil. Word order changes; words like chat and map stay." },
  { title: "Speak", text: "Your voice says it in Tamil, timed to the same moment in the video." },
];
const SRC = ["Chat", "mein", "batao,", "next", "kaunsa", "map", "khelein?"];
const DST = ["Chat-ல", "சொல்லுங்க,", "அடுத்து", "எந்த", "map", "விளையாடலாம்?"];
const KEEP = (w: string) => /^(chat|map)/i.test(w);

function Visual({ stage }: { stage?: number }) {
  const voice = useMemo(() => speechEnvelope(90, 5), []);
  const noise = useMemo(() => speechEnvelope(160, 99).map((v) => 0.15 + v * 0.35), []);
  const show = (i: number) => (stage === undefined ? undefined : { opacity: stage === i ? 1 : 0 });
  return (
    <div className="relative h-[300px] rounded-media border border-mist bg-surface sm:h-[340px]">
      <div data-v="0" className="absolute inset-0 grid place-items-center px-8" style={show(0)}>
        <div className="relative w-full">
          <div data-noise className="absolute inset-0 opacity-70">
            <Waveform samples={noise} hue="var(--slate)" height={160} strokeWidth={1.5} />
          </div>
          <Waveform samples={voice} hue="var(--hi)" height={160} />
          <p className="mt-3 text-center text-sm text-slate">Voice, plus background noise</p>
        </div>
      </div>
      <div data-v="1" className="absolute inset-0 flex flex-wrap content-center items-center justify-center gap-2 px-8" style={show(1)}>
        {SRC.map((w) => (
          <span key={w} data-word className={`rounded-panel border px-3 py-1.5 font-display text-xl ${KEEP(w) ? "border-fg" : "border-[var(--hi)]"}`}>
            {w}
          </span>
        ))}
      </div>
      <div data-v="2" className="absolute inset-0 flex flex-col justify-center gap-6 px-8" style={show(2)}>
        <div className="flex flex-wrap gap-2 opacity-40">
          {SRC.map((w) => (
            <span key={w} className={`rounded-panel border px-2.5 py-1 font-display ${KEEP(w) ? "border-fg" : "border-mist"}`}>{w}</span>
          ))}
        </div>
        <div className="flex flex-wrap gap-2" lang="ta">
          {DST.map((w) => (
            <span key={w} data-tword className={`rounded-panel border px-3 py-1.5 font-display text-xl ${KEEP(w) ? "border-fg" : "border-[var(--ta)]"}`}>
              {w}
            </span>
          ))}
        </div>
        <p className="text-sm text-slate">Outlined in ink: kept in English, in a new position.</p>
      </div>
      <div data-v="3" className="absolute inset-0 grid place-items-center px-8" style={show(3)}>
        <div className="w-full">
          <Waveform samples={voice} hue="var(--ta)" height={160} />
          <p className="mt-3 text-center font-display text-lg">your voice, in Tamil</p>
        </div>
      </div>
    </div>
  );
}

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
        scrollTrigger: { trigger: root.current, start: "top top", end: "+=300%", scrub: true, pin: true },
      });
      tl.to("[data-noise]", { autoAlpha: 0, duration: 1 })
        .to("[data-progress]", { scaleY: 0.25, duration: 1 }, 0)
        .to(v(0), { autoAlpha: 0, duration: 0.3 })
        .to(v(1), { autoAlpha: 1, duration: 0.3 }, "<")
        .to(t(0), { opacity: 0.35, duration: 0.3 }, "<")
        .to(t(1), { opacity: 1, duration: 0.3 }, "<")
        .from("[data-word]", { y: 16, autoAlpha: 0, stagger: 0.1, duration: 0.5 })
        .to("[data-progress]", { scaleY: 0.5, duration: 1 }, "<")
        .to(v(1), { autoAlpha: 0, duration: 0.3 })
        .to(v(2), { autoAlpha: 1, duration: 0.3 }, "<")
        .to(t(1), { opacity: 0.35, duration: 0.3 }, "<")
        .to(t(2), { opacity: 1, duration: 0.3 }, "<")
        .from("[data-tword]", { x: -24, autoAlpha: 0, stagger: 0.12, duration: 0.5 })
        .to("[data-progress]", { scaleY: 0.75, duration: 1 }, "<")
        .to(v(2), { autoAlpha: 0, duration: 0.3 })
        .to(v(3), { autoAlpha: 1, duration: 0.3 }, "<")
        .to(t(2), { opacity: 0.35, duration: 0.3 }, "<")
        .to(t(3), { opacity: 1, duration: 0.3 }, "<")
        .to("[data-progress]", { scaleY: 1, duration: 1 });
    },
    { scope: root, dependencies: [reduced], revertOnUpdate: true },
  );

  if (reduced) {
    return (
      <section aria-labelledby="story-h" className="mx-auto max-w-6xl px-4 py-[clamp(80px,12vh,160px)] sm:px-8">
        <h2 id="story-h" className="font-display text-[2.441rem] font-semibold">How a line gets dubbed</h2>
        <ol className="mt-10 grid gap-10">
          {STAGES.map((s, i) => (
            <li key={s.title} className="grid gap-6 md:grid-cols-[1fr_1.4fr]">
              <div>
                <p className="font-display text-xl font-semibold">{i + 1}. {s.title}</p>
                <p className="mt-2 text-slate">{s.text}</p>
              </div>
              <Visual stage={i} />
            </li>
          ))}
        </ol>
      </section>
    );
  }

  return (
    <section ref={root} aria-labelledby="story-h" className="flex min-h-svh items-center">
      <div className="mx-auto grid w-full max-w-6xl gap-10 px-4 py-16 sm:px-8 md:grid-cols-[1fr_1.4fr] md:items-center">
        <div className="flex gap-6">
          <div className="relative w-[2px] shrink-0 rounded-chip bg-mist" aria-hidden>
            <div data-progress className="absolute inset-0 origin-top scale-y-0 rounded-chip bg-fg" />
          </div>
          <div>
            <h2 id="story-h" className="font-display text-[clamp(1.9rem,4vw,2.441rem)] font-semibold leading-tight">How a line gets dubbed</h2>
            <ol className="mt-8 space-y-6">
              {STAGES.map((s, i) => (
                <li key={s.title} data-t={i}>
                  <p className="font-display text-xl font-semibold">
                    <span className="tnum mr-2 text-slate">{i + 1}</span>
                    {s.title}
                  </p>
                  <p className="mt-1 max-w-[40ch] text-slate">{s.text}</p>
                </li>
              ))}
            </ol>
          </div>
        </div>
        <Visual />
      </div>
    </section>
  );
}
