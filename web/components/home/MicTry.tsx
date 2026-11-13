"use client";
import { Lock, Mic, MicOff } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { VoiceBars } from "@/components/voice/VoiceBars";
import { VoiceOrb } from "@/components/voice/VoiceOrb";
import { useMic } from "@/lib/useMic";

/** A real voice component on the landing page: the visitor's own mic drives the orb and the bars, locally. */
export function MicTry() {
  const mic = useMic();
  const on = mic.state === "on";
  return (
    <section aria-labelledby="mic-h" className="px-3 py-24 sm:px-5 sm:py-32">
      <div data-reveal className="theme-dark relative mx-auto max-w-[84rem] overflow-hidden rounded-[32px] bg-bg text-fg">
        <div aria-hidden className="aura" />
        <div className="relative mx-auto grid max-w-6xl items-center gap-14 px-6 py-20 sm:px-10 sm:py-28 lg:grid-cols-2">
          <div>
            <p className="eyebrow">Try it</p>
            <h2 id="mic-h" className="h-display mt-4 text-[clamp(2.6rem,6vw,4.75rem)]">
              See your voice <em>move.</em>
            </h2>
            <p className="mt-5 max-w-[46ch] text-[1.08rem] text-muted">
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
          </div>

          <div className="flex flex-col items-center">
            <VoiceOrb size="min(72vw, 340px)" analyser={mic.analyser} />
            <div className="mt-10 w-full max-w-md">
              <VoiceBars analyser={mic.analyser} active={false} bars={56} height={72} colors={["--hi", "--bn", "--te", "--en", "--ta"]} />
            </div>
            <p className="mt-4 flex items-center gap-2 text-sm text-muted" role="status">
              <span className={`size-2 rounded-full ${on ? "pulse-dot bg-ok" : "bg-muted"}`} />
              {on ? "Listening to your mic" : "Mic is off"}
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
