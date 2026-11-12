"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Waveform, speechEnvelope } from "@/components/voice/Waveform";
import { DelayBadge } from "@/components/ui/DelayBadge";
import { api, type Dashboard } from "@/lib/api";
import { lang } from "@/lib/langs";
import { useReducedMotion } from "@/lib/hooks";

const LINE: Record<string, string> = {
  src: "Bhai ye clutch moment tha, full send!",
  "ta-IN": "ப்ரோ, இது clutch moment, full send!",
  "bn-IN": "ভাই, এটা clutch moment ছিল, full send!",
  "te-IN": "బ్రో, ఇది clutch moment, full send!",
  "en-IN": "Bro, that was a clutch moment, full send!",
};
const TRACKS = [
  { key: "src", label: "Original" },
  { key: "ta-IN", label: "Tamil" },
  { key: "bn-IN", label: "Bengali" },
];

export function TwoModes() {
  const [track, setTrack] = useState("ta-IN");
  const [liveIdx, setLiveIdx] = useState(0);
  const [delay, setDelay] = useState<number | null>(null);
  const reduced = useReducedMotion();
  const wave = useMemo(() => speechEnvelope(80, 3), []);
  const liveLangs = ["ta-IN", "bn-IN", "te-IN", "en-IN"];

  useEffect(() => {
    if (reduced) return;
    const id = setInterval(() => setLiveIdx((i) => (i + 1) % liveLangs.length), 2600);
    return () => clearInterval(id);
  }, [reduced, liveLangs.length]);
  useEffect(() => {
    api<Dashboard>("/api/dashboard")
      .then((d) => !d.mock_providers && setDelay(d.live.p50_ms))
      .catch(() => {});
  }, []);

  const hue = track === "src" ? "var(--hi)" : lang(track).hue;
  const liveLang = liveLangs[liveIdx];
  return (
    <section aria-labelledby="modes-h" className="mx-auto max-w-6xl px-4 py-[clamp(80px,12vh,160px)] sm:px-8">
      <h2 id="modes-h" className="font-display text-[clamp(1.9rem,4vw,2.441rem)] font-semibold">Two ways to use it</h2>
      <div className="mt-10 grid gap-10 md:grid-cols-2">
        <article>
          <div className="relative aspect-[9/12] overflow-hidden rounded-media bg-[#14161f] text-[#eceef3] sm:aspect-[4/5]">
            <div className="absolute inset-x-0 top-0 flex gap-1.5 p-4" role="tablist" aria-label="Audio track">
              {TRACKS.map((t) => (
                <button
                  key={t.key}
                  role="tab"
                  aria-selected={track === t.key}
                  onClick={() => setTrack(t.key)}
                  className={`rounded-chip px-3.5 py-1.5 font-display text-sm ${track === t.key ? "bg-[#eceef3] text-[#14161f]" : "bg-white/10 text-white/85 hover:bg-white/20"}`}
                >
                  {t.label}
                </button>
              ))}
            </div>
            <div className="absolute inset-x-6 top-1/3">
              <Waveform samples={wave} hue="var(--hi)" toHue={hue} height={90} />
            </div>
            <p lang={track === "src" ? "hi" : lang(track).short} className="absolute inset-x-6 bottom-16 text-center font-display text-xl leading-snug">
              <span className="border-b-2 pb-0.5" style={{ borderColor: hue }}>{LINE[track]}</span>
            </p>
            <div className="absolute inset-x-6 bottom-6 h-1 rounded-chip bg-white/15">
              <div className="voice-ribbon h-full w-2/3 rounded-chip" style={{ ["--to" as string]: hue }} />
            </div>
            <span className="absolute right-4 bottom-9 text-[11px] text-white/60">AI-dubbed</span>
          </div>
          <h3 className="mt-6 font-display text-2xl font-semibold">Studio</h3>
          <p className="mt-2 max-w-[46ch] text-slate">Upload a reel or short up to 3 minutes. Get a dubbed MP4 and subtitles for each language, with your background music kept.</p>
          <Link href="/studio" className="mt-3 inline-block font-display underline underline-offset-4">Dub a video</Link>
        </article>

        <article>
          <div className="relative aspect-[9/12] overflow-hidden rounded-media bg-[#0e1016] text-[#eceef3] sm:aspect-[4/5]">
            <div className="absolute inset-x-4 top-4 aspect-video rounded-panel bg-white/[0.06]" aria-hidden>
              <span className="absolute left-3 top-3 rounded-chip bg-[#e05468] px-2 py-0.5 text-[11px] font-semibold">LIVE</span>
            </div>
            <div className="absolute inset-x-4 top-[calc(1rem+((100%-2rem)*9/16)+1rem)] flex flex-wrap gap-1.5">
              {liveLangs.map((c) => (
                <span key={c} className="inline-flex items-center gap-1.5 rounded-chip bg-white/10 px-2.5 py-1 text-xs">
                  <span className="size-2 rounded-full" style={{ background: lang(c).hue }} />
                  {lang(c).native}
                </span>
              ))}
            </div>
            <p lang={lang(liveLang).short} className="absolute inset-x-6 bottom-16 text-center font-display text-xl leading-snug" aria-live="off">
              <span className="border-b-2 pb-0.5" style={{ borderColor: lang(liveLang).hue }}>{LINE[liveLang]}</span>
            </p>
            {delay != null && (
              <div className="absolute inset-x-0 bottom-5 flex justify-center text-fg">
                <DelayBadge ms={delay} />
              </div>
            )}
          </div>
          <h3 className="mt-6 font-display text-2xl font-semibold">Live</h3>
          <p className="mt-2 max-w-[46ch] text-slate">Stream in Hindi on YouTube. Viewers open your link, pick a language, and hear you dubbed a few seconds behind, with captions.</p>
          <Link href="/live" className="mt-3 inline-block font-display underline underline-offset-4">Go live</Link>
        </article>
      </div>
      <p className="mt-6 text-sm text-slate">Illustrations of the player. Your own reel and stream appear here once dubbed.</p>
    </section>
  );
}
