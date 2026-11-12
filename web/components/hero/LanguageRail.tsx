"use client";
import { useState } from "react";
import { LanguageChip } from "@/components/ui/LanguageChip";
import { LANGS, lang } from "@/lib/langs";

// The same line in each language (hand-checked; English words kept as creators say them).
const SENTENCE: Record<string, string> = {
  "hi-IN": "Chat में बताओ, next कौनसा map खेलें?",
  "ta-IN": "Chat-ல சொல்லுங்க, அடுத்து எந்த map விளையாடலாம்?",
  "bn-IN": "Chat-এ বলো, এরপর কোন map খেলব?",
  "te-IN": "Chat లో చెప్పండి, తర్వాత ఏ map ఆడదాం?",
  "en-IN": "Tell me in chat, which map should we play next?",
};

export function LanguageRail() {
  const [active, setActive] = useState("ta-IN");
  const l = lang(active);
  return (
    <section aria-labelledby="rail-h" className="border-y border-mist">
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-8">
        <h2 id="rail-h" className="font-display text-[1.563rem] font-semibold">
          One line, five ways
        </h2>
        <div role="radiogroup" aria-label="Languages" className="mt-6 flex gap-3 overflow-x-auto pb-2 [scrollbar-width:thin]">
          {LANGS.map((x) => (
            <LanguageChip key={x.code} code={x.code} role="radio" selected={x.code === active} onClick={() => setActive(x.code)} onHover={() => setActive(x.code)} />
          ))}
        </div>
        <p lang={l.short} className="mt-8 min-h-[2.6em] font-display text-[clamp(1.4rem,3.2vw,2.2rem)] leading-snug" aria-live="polite">
          <span className="border-b-[3px] pb-1" style={{ borderColor: l.hue }}>
            {SENTENCE[active]}
          </span>
        </p>
        <p className="mt-4 text-sm text-slate">Words creators say in English, like chat and map, stay in English.</p>
      </div>
    </section>
  );
}
