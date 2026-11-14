"use client";
import { useEffect, useRef, useState } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";
import { ArrowRight, AudioLines, Captions, Mic, Music2, Radio, Sparkles } from "lucide-react";
import { LinkButton } from "@/components/ui/Button";
import { LanguageChip } from "@/components/ui/LanguageChip";
import { VoiceBars } from "@/components/voice/VoiceBars";
import { VoiceOrb } from "@/components/voice/VoiceOrb";
import { useReducedMotion } from "@/lib/hooks";
import { HEADLINE, lang } from "@/lib/langs";

gsap.registerPlugin(ScrollTrigger, useGSAP);

const SCRIPTS = ["hi-IN", "ta-IN", "bn-IN", "te-IN"];
const TARGETS = ["ta-IN", "bn-IN", "te-IN", "en-IN"];
// The same line in each language (hand-checked; English words kept as creators say them).
const SENTENCE: Record<string, string> = {
  "hi-IN": "Chat में बताओ, next कौनसा map खेलें?",
  "ta-IN": "Chat-ல சொல்லுங்க, அடுத்து எந்த map விளையாடலாம்?",
  "bn-IN": "Chat-এ বলো, এরপর কোন map খেলব?",
  "te-IN": "Chat లో చెప్పండి, తర్వాత ఏ map ఆడదాం?",
  "en-IN": "Tell me in chat, which map should we play next?",
};

export function Hero() {
  const root = useRef<HTMLElement>(null);
  const reduced = useReducedMotion();
  const [script, setScript] = useState(0);
  const [target, setTarget] = useState("ta-IN");
  const [auto, setAuto] = useState(true);

  useEffect(() => {
    if (reduced) return;
    const id = setInterval(() => setScript((s) => (s + 1) % SCRIPTS.length), 2600);
    return () => clearInterval(id);
  }, [reduced]);
  useEffect(() => {
    if (reduced || !auto) return;
    const id = setInterval(() => setTarget((t) => TARGETS[(TARGETS.indexOf(t) + 1) % TARGETS.length]), 3400);
    return () => clearInterval(id);
  }, [reduced, auto]);

  useGSAP(
    () => {
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
      const tl = gsap.timeline({ defaults: { ease: "power3.out" } });
      tl.fromTo("[data-h='eyebrow']", { autoAlpha: 0, y: 12 }, { autoAlpha: 1, y: 0, duration: 0.6 })
        .fromTo("[data-h='line']", { autoAlpha: 0, yPercent: 110 }, { autoAlpha: 1, yPercent: 0, duration: 1.1, stagger: 0.12, ease: "expo.out" }, "-=0.35")
        .fromTo("[data-h='fade']", { autoAlpha: 0, y: 16 }, { autoAlpha: 1, y: 0, duration: 0.7, stagger: 0.09 }, "-=0.7")
        .fromTo("[data-h='console']", { autoAlpha: 0, y: 70, scale: 0.97 }, { autoAlpha: 1, y: 0, scale: 1, duration: 1.2, ease: "expo.out" }, "-=0.55");
      gsap.to("[data-h='drift']", { yPercent: -8, ease: "none", scrollTrigger: { trigger: root.current, start: "top top", end: "bottom top", scrub: true } });
    },
    { scope: root },
  );

  const t = lang(target);
  const s = lang(SCRIPTS[script]);
  return (
    <section ref={root} className="relative px-5 pb-16 pt-14 sm:px-8 sm:pt-20">
      <div className="mx-auto max-w-4xl text-center">
        <p data-h="eyebrow" className="gs-hide eyebrow inline-flex items-center gap-2 rounded-chip border border-line bg-surface/70 px-3.5 py-1.5 backdrop-blur">
          <Sparkles aria-hidden className="size-3.5" />
          Voice AI for Indian creators
        </p>
        <h1 className="h-display mt-7 text-[clamp(3.4rem,10.5vw,7.75rem)] leading-[0.92]">
          <span className="block overflow-hidden pb-[0.14em]">
            <span data-h="line" className="gs-hide block">One voice.</span>
          </span>
          <span className="-mt-[0.14em] block overflow-hidden pb-[0.2em]">
            <span data-h="line" className="gs-hide block"><em>Every language.</em></span>
          </span>
        </h1>
        <p data-h="fade" aria-hidden className="gs-hide -mt-1 h-11 font-indic text-[clamp(1.35rem,3.2vw,2rem)] font-medium">
          <span key={s.code} lang={s.short} className="rise inline-flex items-center gap-3">
            <span className="size-2 rounded-full" style={{ background: s.hue }} />
            {HEADLINE[s.code]}
          </span>
        </p>
        <p data-h="fade" className="gs-hide mx-auto mt-5 max-w-[54ch] text-[1.1rem] text-muted">
          Bharat Dub turns your Hindi or Hinglish video, or your live stream, into Tamil, Bengali, Telugu and English. In your own voice, with
          your music kept.
        </p>
        <div data-h="fade" className="gs-hide mt-9 flex flex-wrap justify-center gap-3">
          <LinkButton href="/studio" size="lg">
            Dub a video
            <ArrowRight aria-hidden className="size-4 transition-transform group-hover:translate-x-0.5" />
          </LinkButton>
          <LinkButton href="/streamer" size="lg" variant="secondary">
            <Radio aria-hidden className="size-4" />
            Go live
          </LinkButton>
        </div>
      </div>

      <div data-h="drift" className="relative mx-auto mt-16 max-w-5xl">
        {/* Hatched rails behind the console */}
        <span aria-hidden className="tex-hatch absolute -inset-x-14 bottom-16 top-10 -z-10 hidden rounded-[28px] border border-line xl:block" />
        <div data-h="console" className="gs-hide card card-lift p-2">
          <div className="flex items-center justify-between px-4 py-2.5">
            <span className="eyebrow">How a line travels</span>
            <span className="eyebrow">Illustration</span>
          </div>
          <div className="grid gap-2 md:grid-cols-[1fr_auto_1fr]">
            <div className="flex flex-col rounded-[18px] bg-sunken p-6 text-left">
              <p className="eyebrow flex items-center gap-2">
                <Mic aria-hidden className="size-3.5" />
                You say · Hindi
              </p>
              <p lang="hi" className="mt-4 min-h-[3.4em] flex-1 font-indic text-[1.35rem] font-medium leading-snug sm:text-2xl">
                {SENTENCE["hi-IN"]}
              </p>
              <VoiceBars colors={["--hi"]} bars={40} height={48} className="mt-4" />
            </div>
            <div className="grid place-items-center px-3 py-1">
              <VoiceOrb size={92} />
            </div>
            <div className="theme-dark stage flex flex-col overflow-hidden rounded-[18px] p-6 text-left text-fg" style={{ ["--glow" as string]: t.hue }}>
              <p className="eyebrow flex items-center gap-2">
                <AudioLines aria-hidden className="size-3.5" />
                Viewers hear · {t.name}
              </p>
              <p key={target} lang={t.short} className="rise mt-4 min-h-[3.4em] flex-1 font-indic text-[1.35rem] font-medium leading-snug sm:text-2xl" aria-live="off">
                {SENTENCE[target]}
              </p>
              <VoiceBars key={`bars-${target}`} colors={[t.hue]} bars={40} height={48} seed={7} className="mt-4" />
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-4 px-3 pb-2 pt-4">
            <div role="radiogroup" aria-label="Dub language" className="flex flex-wrap gap-2">
              {TARGETS.map((c) => (
                <LanguageChip
                  key={c}
                  code={c}
                  role="radio"
                  selected={c === target}
                  onClick={() => {
                    setAuto(false);
                    setTarget(c);
                  }}
                />
              ))}
            </div>
            <ul className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-muted">
              <li className="flex items-center gap-1.5"><Mic aria-hidden className="size-4" />Your voice</li>
              <li className="flex items-center gap-1.5"><Music2 aria-hidden className="size-4" />Music kept</li>
              <li className="flex items-center gap-1.5"><Captions aria-hidden className="size-4" />Captions</li>
            </ul>
          </div>
        </div>
        <p className="mt-4 text-center text-sm text-muted">Words creators say in English, like chat and map, stay in English.</p>
      </div>
    </section>
  );
}
