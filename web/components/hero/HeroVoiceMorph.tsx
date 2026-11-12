"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { gsap } from "gsap";
import { SplitText } from "gsap/SplitText";
import { useGSAP } from "@gsap/react";
import { LinkButton } from "@/components/ui/Button";
import { Waveform, speechEnvelope } from "@/components/voice/Waveform";
import { useAudioLevel } from "@/components/voice/useAudioLevel";
import { useReducedMotion } from "@/lib/hooks";
import { HEADLINE, lang } from "@/lib/langs";

gsap.registerPlugin(SplitText, useGSAP);

const SEQUENCE = ["hi-IN", "ta-IN", "bn-IN", "en-IN"] as const;
const HERO_CLIP = process.env.NEXT_PUBLIC_HERO_CLIP; // a real, consented 6 s clip; Play is hidden without it

function restingLang(): string {
  if (typeof navigator === "undefined") return "en-IN";
  const pref = navigator.language.toLowerCase().split("-")[0];
  const hit = Object.keys(HEADLINE).find((c) => c.startsWith(pref));
  return hit ?? "en-IN";
}

export function HeroVoiceMorph() {
  const root = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();
  const [current, setCurrent] = useState<string>("hi-IN");
  const [rest, setRest] = useState<string>("en-IN");
  const samples = useMemo(() => speechEnvelope(150, 11), []);
  const order = useMemo(() => {
    // Hindi -> Tamil -> Bengali -> English, then rest on the visitor's language if we support it.
    const seq: string[] = [...SEQUENCE];
    if (rest !== "en-IN") seq.push(rest);
    return seq;
  }, [rest]);

  useEffect(() => {
    setRest(restingLang());
  }, []);

  useGSAP(
    () => {
      const lines = gsap.utils.toArray<HTMLElement>("[data-line]", root.current);
      const byLang = (c: string) => lines.find((l) => l.dataset.line === c)!;
      if (reduced) {
        lines.forEach((l) => gsap.set(l, { autoAlpha: l.dataset.line === rest ? 1 : 0 }));
        setCurrent(rest);
        return;
      }
      // Words, not characters: splitting Indic scripts per character breaks conjuncts and matras.
      const splits = new Map(lines.map((l) => [l.dataset.line!, new SplitText(l, { type: "words", wordsClass: "wdth inline-block" })]));
      lines.forEach((l) => gsap.set(l, { autoAlpha: 0 }));
      const tl = gsap.timeline({ delay: 0.25 });
      const first = splits.get(order[0])!;
      tl.set(byLang(order[0]), { autoAlpha: 1 })
        .from(first.words, { autoAlpha: 0, "--wdth": 60, duration: 0.5, stagger: 0.14, ease: "power3.out" });
      for (let i = 1; i < order.length; i++) {
        const prev = splits.get(order[i - 1])!;
        const next = splits.get(order[i])!;
        const code = order[i];
        tl.to(prev.words, { "--wdth": 50, autoAlpha: 0, duration: 0.45, stagger: 0.04, ease: "expo.in" }, "+=0.35")
          .call(() => setCurrent(code))
          .set(byLang(order[i - 1]), { autoAlpha: 0 })
          .set(byLang(code), { autoAlpha: 1 })
          .fromTo(next.words, { "--wdth": 50, autoAlpha: 0 }, { "--wdth": 100, autoAlpha: 1, duration: 0.55, stagger: 0.05, ease: "expo.out" });
      }
      // Skippable: scrolling jumps to the final state.
      const skip = () => tl.progress(1);
      window.addEventListener("wheel", skip, { once: true, passive: true });
      window.addEventListener("touchmove", skip, { once: true, passive: true });
      return () => {
        window.removeEventListener("wheel", skip);
        window.removeEventListener("touchmove", skip);
        splits.forEach((s) => s.revert());
      };
    },
    { scope: root, dependencies: [reduced, order.join()], revertOnUpdate: true },
  );

  // Optional real clip: headline width and ribbon follow live amplitude.
  const audioRef = useRef<HTMLAudioElement>(null);
  const [ctx, setCtx] = useState<AudioContext | null>(null);
  const [src, setSrc] = useState<MediaElementAudioSourceNode | null>(null);
  const level = useAudioLevel(src, ctx);
  const [playing, setPlaying] = useState(false);
  const play = async () => {
    const el = audioRef.current;
    if (!el) return;
    if (!ctx) {
      const c = new AudioContext();
      const s = c.createMediaElementSource(el);
      s.connect(c.destination);
      setCtx(c);
      setSrc(s);
    }
    if (el.paused) {
      await el.play();
      setPlaying(true);
    } else {
      el.pause();
      setPlaying(false);
    }
  };
  const breathing = playing && !reduced ? 70 + level * 45 : undefined;

  const hue = lang(current).hue;
  return (
    <section ref={root} className="mx-auto flex min-h-[calc(100svh-4rem)] max-w-6xl flex-col justify-center px-4 py-20 sm:px-8">
      <h1
        className="grid font-display text-[clamp(2.6rem,7vw,5.4rem)] font-semibold leading-[1.08]"
        style={breathing ? { ["--wdth" as string]: breathing } : undefined}
        aria-label="One voice. Every language."
      >
        {Object.entries(HEADLINE).map(([code, text]) => (
          <span key={code} data-line={code} lang={code.slice(0, 2)} aria-hidden className="wdth [grid-area:1/1]" style={{ visibility: code === "hi-IN" ? undefined : "hidden" }}>
            {text}
          </span>
        ))}
      </h1>

      <div className="mt-10 transition-[filter] duration-700" aria-hidden>
        <Waveform samples={samples} hue="var(--hi)" toHue={current === "hi-IN" ? "var(--hi)" : hue} height={110} gain={breathing ? 0.6 + level * 1.4 : 1} />
      </div>

      <p className="mt-10 max-w-[56ch] text-[1.15rem] text-slate">
        Dub your videos, or your live stream, into Indian languages in your own voice.
      </p>
      <div className="mt-8 flex flex-wrap items-center gap-3">
        <LinkButton href="/studio" size="lg">Dub a video</LinkButton>
        <LinkButton href="/live" size="lg" variant="secondary">Go live</LinkButton>
        {HERO_CLIP && (
          <>
            <button
              type="button"
              onClick={play}
              aria-label={playing ? "Pause sample" : "Play a 6 second sample: Hindi, then the Tamil dub"}
              className="ml-2 grid size-14 place-items-center rounded-chip border border-mist bg-surface hover:border-fg"
            >
              {playing ? (
                <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden><rect x="3" y="2" width="3.5" height="12" rx="1" fill="currentColor" /><rect x="9.5" y="2" width="3.5" height="12" rx="1" fill="currentColor" /></svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden><path d="M4 2.5v11l9-5.5z" fill="currentColor" /></svg>
              )}
            </button>
            <audio ref={audioRef} src={HERO_CLIP} preload="none" crossOrigin="anonymous" onEnded={() => setPlaying(false)} />
          </>
        )}
      </div>
    </section>
  );
}
