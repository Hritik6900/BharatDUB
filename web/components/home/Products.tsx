"use client";
import { useEffect, useState } from "react";
import { ArrowRight, BookA, Captions, Check, Clapperboard, Mic, Music2, Play, Radio, type LucideIcon } from "lucide-react";
import { LinkButton } from "@/components/ui/Button";
import { DelayBadge } from "@/components/ui/DelayBadge";
import { VoiceBars } from "@/components/voice/VoiceBars";
import { api, type Dashboard } from "@/lib/api";
import { useReducedMotion } from "@/lib/hooks";
import { lang } from "@/lib/langs";
import { SectionHead } from "./Sections";

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
const LIVE_LANGS = ["ta-IN", "bn-IN", "te-IN", "en-IN"];

function StudioMock() {
  const [track, setTrack] = useState("ta-IN");
  const hue = track === "src" ? "var(--hi)" : lang(track).hue;
  return (
    <div className="theme-dark relative flex aspect-[4/3] flex-col justify-between overflow-hidden rounded-[18px] bg-bg p-5 text-fg">
      <div role="tablist" aria-label="Audio track" className="flex gap-1.5">
        {TRACKS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={track === t.key}
            onClick={() => setTrack(t.key)}
            className={`rounded-chip px-3.5 py-1.5 text-sm transition-colors ${track === t.key ? "bg-fg text-on-fg" : "bg-white/10 hover:bg-white/20"}`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <VoiceBars key={track} colors={[hue]} bars={44} height={72} seed={3} />
      <div>
        <p key={track} lang={track === "src" ? "hi" : lang(track).short} className="rise text-center font-indic text-lg font-medium leading-snug sm:text-xl">
          {LINE[track]}
        </p>
        <div className="mt-4 flex items-center gap-3">
          <span className="grid size-8 shrink-0 place-items-center rounded-full bg-fg text-on-fg">
            <Play aria-hidden className="size-3.5 translate-x-px fill-current" />
          </span>
          <span className="h-1 flex-1 overflow-hidden rounded-chip bg-white/15">
            <span className="block h-full w-2/3 rounded-chip transition-colors duration-500" style={{ background: hue }} />
          </span>
          <span className="text-[11px] text-muted">AI-dubbed</span>
        </div>
      </div>
    </div>
  );
}

function LiveMock() {
  const [i, setI] = useState(0);
  const [delay, setDelay] = useState<number | null>(null);
  const reduced = useReducedMotion();
  useEffect(() => {
    if (reduced) return;
    const id = setInterval(() => setI((x) => (x + 1) % LIVE_LANGS.length), 2600);
    return () => clearInterval(id);
  }, [reduced]);
  useEffect(() => {
    // Only a measured delay from real (non-mock) sessions is ever shown here.
    api<Dashboard>("/api/dashboard")
      .then((d) => !d.mock_providers && setDelay(d.live.p50_ms))
      .catch(() => {});
  }, []);
  const code = LIVE_LANGS[i];
  return (
    <div className="theme-dark relative flex aspect-[4/3] flex-col justify-between overflow-hidden rounded-[18px] bg-bg p-5 text-fg">
      <div className="flex items-center justify-between">
        <span className="inline-flex items-center gap-1.5 rounded-chip bg-danger px-2.5 py-1 text-[11px] font-semibold text-white">
          <span className="pulse-dot size-1.5 rounded-full bg-white" />
          LIVE
        </span>
        <DelayBadge ms={delay} />
      </div>
      <VoiceBars colors={["--hi", lang(code).hue]} bars={44} height={72} seed={11} />
      <div>
        <p key={code} lang={lang(code).short} className="rise text-center font-indic text-lg font-medium leading-snug sm:text-xl">
          {LINE[code]}
        </p>
        <ul className="mt-4 flex flex-wrap justify-center gap-1.5">
          {LIVE_LANGS.map((c) => (
            <li key={c} className={`inline-flex items-center gap-1.5 rounded-chip px-2.5 py-1 font-indic text-xs transition-colors ${c === code ? "bg-fg text-on-fg" : "bg-white/10"}`}>
              <span className="size-1.5 rounded-full" style={{ background: lang(c).hue }} />
              {lang(c).native}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

interface Product {
  no: string;
  icon: LucideIcon;
  name: string;
  title: string;
  text: string;
  points: string[];
  href: string;
  cta: string;
  mock: React.ReactNode;
}

const FEATURES = [
  { icon: Mic, title: "Your own voice", text: "Record 20 to 30 seconds once. Every dub then sounds like you, not a narrator." },
  { icon: Music2, title: "Music stays", text: "Your voice is lifted off the background, so the music and game sound survive the dub." },
  { icon: BookA, title: "Words that never change", text: "Your name, game titles and catchphrases go in a glossary and are kept as they are." },
  { icon: Captions, title: "Subtitles included", text: "Every language comes with a subtitle file timed to the dubbed lines." },
];

export function Products() {
  const products: Product[] = [
    {
      no: "01",
      icon: Clapperboard,
      name: "Studio",
      title: "For videos you have already made",
      text: "Upload a reel, short or clip up to 3 minutes. You get it back dubbed, one video per language.",
      points: ["MP4 and subtitles for each language", "Edit any line and only that line is re-voiced", "Compare original and dub on one timeline"],
      href: "/studio",
      cta: "Dub a video",
      mock: <StudioMock />,
    },
    {
      no: "02",
      icon: Radio,
      name: "Live",
      title: "For streams happening right now",
      text: "Stream in Hindi on YouTube as usual. Viewers open your link, pick a language and hear you dubbed a few seconds behind.",
      points: ["Live captions in each language", "Viewers chat in their language, you read it in yours", "Chat overlay for OBS"],
      href: "/live",
      cta: "Go live",
      mock: <LiveMock />,
    },
  ];
  return (
    <section id="products" className="mx-auto max-w-6xl px-5 py-24 sm:px-8 sm:py-32">
      <SectionHead
        eyebrow="Two products, one voice"
        title={<>Record once. <em>Publish in every language.</em></>}
        lede="Studio and Live share the same voice profile and the same glossary, so you sound like yourself in both."
      />
      <div className="mt-14 grid gap-5 lg:grid-cols-2">
        {products.map((p) => (
          <article key={p.name} data-reveal className="card flex flex-col p-2">
            {p.mock}
            <div className="flex flex-1 flex-col p-6 sm:p-7">
              <p className="eyebrow flex items-center gap-2">
                <span className="tnum">{p.no}</span>
                <span aria-hidden className="h-px w-6 bg-line" />
                <p.icon aria-hidden className="size-3.5" />
                {p.name}
              </p>
              <h3 className="h-display mt-4 text-[2rem] leading-[1.05] sm:text-[2.4rem]">{p.title}</h3>
              <p className="mt-3 text-muted">{p.text}</p>
              <ul className="mt-5 flex-1 space-y-2">
                {p.points.map((x) => (
                  <li key={x} className="flex items-start gap-2.5">
                    <Check aria-hidden className="mt-1 size-4 shrink-0 text-ok" />
                    {x}
                  </li>
                ))}
              </ul>
              <LinkButton href={p.href} variant="secondary" className="mt-7 self-start">
                {p.cta}
                <ArrowRight aria-hidden className="size-4 transition-transform group-hover:translate-x-0.5" />
              </LinkButton>
            </div>
          </article>
        ))}
      </div>
      <p className="mt-4 text-sm text-muted">The two players above are illustrations. Your own reel and stream appear in them once dubbed.</p>

      <ul className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {FEATURES.map((f) => (
          <li key={f.title} data-reveal className="card p-6">
            <f.icon aria-hidden className="size-5" />
            <h3 className="mt-5 font-medium tracking-[-0.01em]">{f.title}</h3>
            <p className="mt-1.5 text-sm text-muted">{f.text}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
