"use client";
import { Lock, Mic, MicOff } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { VoiceBars } from "@/components/voice/VoiceBars";
import { VoiceOrb } from "@/components/voice/VoiceOrb";
import { LANGS } from "@/lib/langs";
import { useMic } from "@/lib/useMic";

/** A real voice component on the landing page: the visitor's own mic drives the orb and the bars, locally. */
export function MicTry() {
  const mic = useMic();
  const on = mic.state === "on";
  return (
    <section aria-labelledby="mic-h" className="px-3 py-20 sm:px-5 sm:py-28">
      <div data-reveal className="theme-dark stage mx-auto max-w-6xl overflow-hidden rounded-[28px] border border-line text-fg" style={{ ["--glow" as string]: "var(--te)" }}>
        <div className="grid items-center gap-10 px-6 py-12 sm:px-12 sm:py-14 lg:grid-cols-[1fr_1.05fr]">
          <div>
            <p className="eyebrow flex items-center gap-2">
              <span className={`size-1.5 rounded-full ${on ? "pulse-dot bg-ok" : "bg-muted"}`} />
              Try it
            </p>
            <h2 id="mic-h" className="h-display mt-4 text-[clamp(2.4rem,5vw,3.9rem)]">
              See your voice <em>move.</em>
            </h2>
            <p className="mt-5 max-w-[44ch] text-[1.05rem] text-muted">
              Turn on your mic and say something. The orb and the bars follow your voice as you speak. It is the same signal Live listens to when
              you stream.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-4">
              {on ? (
                <Button size="lg" variant="secondary" onClick={mic.stop}>
                  <MicOff aria-hidden className="size-4" />
                  Turn off mic
                </Button>
              ) : (
                <Button size="lg" onClick={mic.start} disabled={mic.state === "asking"}>
                  <Mic aria-hidden className="size-4" />
                  {mic.state === "asking" ? "Waiting for permission…" : "Turn on mic"}
                </Button>
              )}
              <p className="flex items-center gap-2 text-sm text-muted">
                <Lock aria-hidden className="size-4" />
                Stays in your browser. Nothing is recorded or sent.
              </p>
            </div>
            {mic.state === "error" && (
              <div className="mt-5 max-w-md">
                <Notice tone="warn">Could not open the microphone: {mic.error}</Notice>
              </div>
            )}
            <div className="mt-9 max-w-md rounded-[14px] border border-white/10 bg-black/35 p-4 backdrop-blur-sm">
              <div className="flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.14em] text-muted" role="status">
                <span>Your mic</span>
                <span>{on ? "Listening" : "Off"}</span>
              </div>
              <VoiceBars analyser={mic.analyser} active={false} bars={52} height={56} colors={["--hi", "--bn", "--te", "--en", "--ta"]} className="mt-2" />
            </div>
          </div>

          {/* Orb system: rings, ripples and the five languages in orbit. Decoration around a real, mic-driven orb. */}
          <div aria-hidden className="relative mx-auto grid aspect-square w-full max-w-[420px] place-items-center" style={{ ["--r" as string]: "min(38vw, 185px)" }}>
            <span className="absolute inset-[4%] rounded-full border border-white/10" />
            <span className="absolute inset-[16%] rounded-full border border-dashed border-white/15" />
            <span className="absolute inset-[28%] rounded-full border border-white/10" />
            <div className="absolute inset-[30%]">
              <span className="ripple" />
              <span className="ripple" style={{ animationDelay: "1s" }} />
              <span className="ripple" style={{ animationDelay: "2s" }} />
            </div>
            <div className="spin-slow absolute inset-0">
              {LANGS.map((l, i) => {
                const a = (360 / LANGS.length) * i;
                return (
                  <span key={l.code} className="absolute left-1/2 top-1/2 size-0" style={{ transform: `rotate(${a}deg) translateY(calc(var(--r) * -1))` }}>
                    <span className="absolute left-0 top-0 block" style={{ transform: `translate(-50%, -50%) rotate(${-a}deg)` }}>
                      <span lang={l.short} className="spin-rev inline-flex items-center gap-2 whitespace-nowrap rounded-chip border border-white/15 bg-surface/90 px-3 py-1.5 font-indic text-sm font-medium shadow-card backdrop-blur">
                        <span className="size-2 rounded-full" style={{ background: l.hue }} />
                        {l.native}
                      </span>
                    </span>
                  </span>
                );
              })}
            </div>
            <VoiceOrb size="44%" analyser={mic.analyser} />
          </div>
        </div>
      </div>
    </section>
  );
}
