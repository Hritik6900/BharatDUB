"use client";
import { useEffect, useState } from "react";
import { ArrowRight, AudioLines, Check, Clapperboard, Cpu, Ear, Film, Headphones, Languages, Mic, MonitorPlay, Play, Radio, Scissors, Timer, Upload, type LucideIcon } from "lucide-react";
import { LinkButton } from "@/components/ui/Button";
import { DelayBadge } from "@/components/ui/DelayBadge";
import { VoiceBars } from "@/components/voice/VoiceBars";
import { VoiceOrb } from "@/components/voice/VoiceOrb";
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

const MUSIC_PATH = "M0 8 Q 6 1 12 8" + Array.from({ length: 19 }, (_, i) => ` T ${(i + 2) * 12} 8`).join("");

function Lane({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-11 shrink-0 font-mono text-[10px] uppercase tracking-[0.14em] text-muted">{label}</span>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

/** Studio: three lanes. Your voice comes off the music, and the dub lands on the same beats. */
function StudioMock() {
  const [track, setTrack] = useState("ta-IN");
  const src = track === "src";
  const hue = src ? "var(--hi)" : lang(track).hue;
  return (
    <div className="theme-dark stage flex aspect-[4/3] flex-col justify-between overflow-hidden rounded-[18px] p-5 text-fg" style={{ ["--glow" as string]: hue }}>
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
      <div aria-hidden className="space-y-2 rounded-[14px] border border-white/10 bg-black/35 p-3.5 backdrop-blur-sm">
        <Lane label="Voice">
          <VoiceBars key={`v-${src}`} colors={[src ? "--hi" : "--muted"]} bars={42} height={24} seed={3} />
        </Lane>
        <Lane label="Music">
          <svg viewBox="0 0 240 16" preserveAspectRatio="none" className="block h-4 w-full">
            <path d={MUSIC_PATH} fill="none" stroke="var(--muted)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
          </svg>
        </Lane>
        <Lane label="Dub">
          <VoiceBars key={`d-${track}`} active={!src} colors={[hue]} bars={42} height={34} seed={3} />
        </Lane>
      </div>
      <div>
        <p key={track} lang={src ? "hi" : lang(track).short} className="rise text-center font-indic text-lg font-medium leading-snug sm:text-xl">
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

/** Live: Hindi goes into the orb, the viewer's language comes out the other side. */
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
  const l = lang(code);
  return (
    <div className="theme-dark stage flex aspect-[4/3] flex-col justify-between overflow-hidden rounded-[18px] p-5 text-fg" style={{ ["--glow" as string]: l.hue }}>
      <div className="flex items-center justify-between">
        <span className="inline-flex items-center gap-1.5 rounded-chip bg-danger px-2.5 py-1 text-[11px] font-semibold text-white">
          <span className="pulse-dot size-1.5 rounded-full bg-white" />
          LIVE
        </span>
        <DelayBadge ms={delay} />
      </div>
      <div aria-hidden>
        <div className="flex items-center gap-2">
          <div className="min-w-0 flex-1">
            <VoiceBars colors={["--hi"]} bars={18} height={52} seed={11} />
          </div>
          <div className="relative grid size-24 shrink-0 place-items-center">
            <span className="ripple" />
            <span className="ripple" style={{ animationDelay: "1s" }} />
            <span className="ripple" style={{ animationDelay: "2s" }} />
            <VoiceOrb size={62} />
          </div>
          <div className="min-w-0 flex-1">
            <VoiceBars key={code} colors={[l.hue]} bars={18} height={52} seed={5} />
          </div>
        </div>
        <div className="mt-1 flex justify-between font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
          <span>Hindi in</span>
          <span>{l.name} out</span>
        </div>
      </div>
      <div>
        <p key={code} lang={l.short} className="rise text-center font-indic text-lg font-medium leading-snug sm:text-xl">
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
const STREAM_LANGS = ["ta-IN", "bn-IN", "te-IN"];

/** Streamer: one voice in, the same voice out in several languages at once. */
function StreamerMock() {
  const [i, setI] = useState(0);
  const reduced = useReducedMotion();
  useEffect(() => {
    if (reduced) return;
    const id = setInterval(() => setI((x) => (x + 1) % STREAM_LANGS.length), 2600);
    return () => clearInterval(id);
  }, [reduced]);
  const code = STREAM_LANGS[i];
  return (
    <div className="theme-dark stage flex aspect-[4/3] flex-col justify-between overflow-hidden rounded-[18px] p-5 text-fg" style={{ ["--glow" as string]: lang(code).hue }}>
      <div className="flex items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1.5 rounded-chip bg-danger px-2.5 py-1 text-[11px] font-semibold text-white">
          <span className="pulse-dot size-1.5 rounded-full bg-white" />
          ON AIR
        </span>
        <span className="inline-flex items-center gap-1.5 rounded-chip bg-white/10 px-2.5 py-1 text-[11px]">
          <Mic aria-hidden className="size-3" />
          Your own voice
        </span>
      </div>
      <div aria-hidden className="flex items-center gap-4">
        <div className="shrink-0 text-center">
          <div className="relative grid size-20 place-items-center">
            <span className="ripple" />
            <span className="ripple" style={{ animationDelay: "1.5s" }} />
            <VoiceOrb size={56} />
          </div>
          <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted">You, Hindi</p>
        </div>
        <ul className="min-w-0 flex-1 space-y-1.5 rounded-[14px] border border-white/10 bg-black/35 p-3 backdrop-blur-sm">
          {STREAM_LANGS.map((c, k) => (
            <li key={c} className="flex items-center gap-2.5">
              <span className={`flex w-[4.5rem] shrink-0 items-center gap-1.5 font-indic text-xs transition-opacity ${c === code ? "" : "opacity-60"}`}>
                <span className="size-1.5 rounded-full" style={{ background: lang(c).hue }} />
                {lang(c).native}
              </span>
              <div className="min-w-0 flex-1">
                <VoiceBars colors={[lang(c).hue]} bars={26} height={22} seed={k * 4 + 2} />
              </div>
            </li>
          ))}
        </ul>
      </div>
      <div>
        <p key={code} lang={lang(code).short} className="rise text-center font-indic text-lg font-medium leading-snug sm:text-xl">
          {LINE[code]}
        </p>
        <p className="mt-3 text-center text-[11px] text-muted">One recording of you, every language at the same time. AI-dubbed.</p>
      </div>
    </div>
  );
}

interface Step {
  icon: LucideIcon;
  label: string;
  text: string;
}

/** What happens inside a mode, one step lighting after the other. */
function Flow({ steps, hue }: { steps: Step[]; hue: string }) {
  const [at, setAt] = useState(0);
  const reduced = useReducedMotion();
  useEffect(() => {
    setAt(0);
    if (reduced) return;
    const id = setInterval(() => setAt((x) => (x + 1) % steps.length), 1700);
    return () => clearInterval(id);
  }, [steps, reduced]);
  if (reduced) {
    return (
      <ol className="theme-dark space-y-2 rounded-[18px] bg-bg p-5 text-sm text-fg">
        {steps.map((s, i) => (
          <li key={s.label} className="flex items-start gap-3">
            <span className="tnum font-mono text-xs text-muted">0{i + 1}</span>
            <span>
              <span className="font-medium">{s.label}.</span> <span className="text-muted">{s.text}</span>
            </span>
          </li>
        ))}
      </ol>
    );
  }
  const now = steps[Math.min(at, steps.length - 1)];
  return (
    <div className="theme-dark rounded-[18px] bg-bg p-5 text-fg">
      <p className="eyebrow flex items-center gap-2">
        <span className="pulse-dot size-1.5 rounded-full" style={{ background: hue }} />
        What is happening
      </p>
      <ol aria-hidden className="mt-4 flex items-center">
        {steps.map((s, i) => (
          <li key={s.label} className={`flex items-center ${i ? "flex-1" : ""}`}>
            {i > 0 && (
              <span className="mx-1 h-px flex-1 overflow-hidden bg-white/15 sm:mx-1.5">
                <span className="block h-full origin-left transition-transform duration-500" style={{ background: hue, transform: `scaleX(${i <= at ? 1 : 0})` }} />
              </span>
            )}
            <span className="relative grid size-9 shrink-0 place-items-center sm:size-10">
              {i === at && <span className="ripple" style={{ animationDuration: "1.7s", borderColor: hue }} />}
              <span
                className={`grid size-full place-items-center rounded-full border transition-colors duration-300 ${
                  i === at ? "border-fg bg-fg text-on-fg" : i < at ? "border-white/30 bg-white/10" : "border-white/15 text-muted"
                }`}
              >
                <s.icon className="size-4" />
              </span>
            </span>
          </li>
        ))}
      </ol>
      <p key={now.label} className="rise mt-4 min-h-[3.25rem] text-sm leading-snug" style={{ animationDuration: "0.35s" }}>
        <span className="tnum mr-2 font-mono text-xs text-muted">
          0{at + 1}/0{steps.length}
        </span>
        <span className="font-medium">{now.label}.</span> <span className="text-muted">{now.text}</span>
      </p>
      <ol className="sr-only">
        {steps.map((s) => (
          <li key={s.label}>
            {s.label}. {s.text}
          </li>
        ))}
      </ol>
    </div>
  );
}

interface Mode {
  no: string;
  icon: LucideIcon;
  name: string;
  tag: string;
  title: string;
  text: string;
  points: string[];
  href: string;
  cta: string;
  hue: string;
  mock: React.ReactNode;
  steps: Step[];
}

const MODES: Mode[] = [
  {
    no: "01",
    icon: Clapperboard,
    name: "Studio",
    tag: "A video you already made",
    title: "For videos you have already made",
    text: "Upload a reel, short or clip up to 3 minutes. You get it back dubbed, one video per language.",
    points: ["MP4 and subtitles for each language", "Edit any line and only that line is re-voiced", "Compare original and dub on one timeline"],
    href: "/studio",
    cta: "Dub a video",
    hue: "var(--ta)",
    mock: <StudioMock />,
    steps: [
      { icon: Upload, label: "Upload", text: "Your reel goes in, up to 3 minutes." },
      { icon: Scissors, label: "Split", text: "Your voice is lifted off the music, so the music can stay." },
      { icon: Ear, label: "Listen", text: "Every line is written down with the moment it was said." },
      { icon: Languages, label: "Translate", text: "Each line is rewritten the way a creator talks, glossary words untouched." },
      { icon: Mic, label: "Voice", text: "The line is spoken in your voice and fitted to the same slot." },
      { icon: Film, label: "Render", text: "Music goes back under the dub. One MP4 and subtitle file per language." },
    ],
  },
  {
    no: "02",
    icon: Radio,
    name: "Streamer",
    tag: "Your stream, your own voice",
    title: "Go live and be heard in your own voice",
    text: "Record your voice once, with your consent. Then stream on YouTube as usual: viewers hear you in their language from your first sentence.",
    points: [
      "Your voice from the first phrase, several languages at once",
      "The dub waits for YouTube's delay, so it lands on your lips",
      "Works with your mic or an OBS virtual cable",
    ],
    href: "/streamer",
    cta: "Set up my stream",
    hue: "var(--bn)",
    mock: <StreamerMock />,
    steps: [
      { icon: Mic, label: "You speak", text: "Hindi or Hinglish into your own mic, exactly as on any stream." },
      { icon: Ear, label: "Heard", text: "Phrases are cut while you are still talking, not after you pause." },
      { icon: Languages, label: "Translated", text: "Every phrase goes to all your languages at once. Captions leave first." },
      { icon: Cpu, label: "Your voice", text: "Our GPU speaks each phrase in the voice you recorded." },
      { icon: Timer, label: "Timed", text: "The dub is held for as long as YouTube runs behind you." },
      { icon: Headphones, label: "Heard by viewers", text: "They pick a language on your link and hear you, on the picture." },
    ],
  },
  {
    no: "03",
    icon: MonitorPlay,
    name: "Live",
    tag: "Any stream that is playing",
    title: "For a stream that is already playing",
    text: "Paste a YouTube link and play it. Viewers on your Bharat Dub link hear it dubbed, with the video held a few seconds so the dub stays in step.",
    points: [
      "Live captions in each language",
      "Stock voices only: a voice is never copied without its owner's consent",
      "Viewers chat in their language, you read it in yours",
    ],
    href: "/live",
    cta: "Dub a stream",
    hue: "var(--te)",
    mock: <LiveMock />,
    steps: [
      { icon: MonitorPlay, label: "A stream plays", text: "The video runs in a browser tab; its sound is the source." },
      { icon: Ear, label: "Heard", text: "Speech is written down phrase by phrase, with the video time it was said at." },
      { icon: Languages, label: "Translated", text: "Kept short when the dub falls behind, so it can catch up." },
      { icon: AudioLines, label: "Spoken", text: "A stock voice for each language speaks the phrase." },
      { icon: Timer, label: "In step", text: "The viewer's video waits a few seconds; each phrase starts at its own moment." },
      { icon: Headphones, label: "Heard by viewers", text: "Picture, dub and captions arrive together." },
    ],
  },
];

export function Products() {
  const [open, setOpen] = useState(1);
  const m = MODES[open];
  return (
    <section id="products" className="mx-auto max-w-6xl px-5 pb-20 pt-24 sm:px-8 sm:pb-24 sm:pt-32">
      <SectionHead
        eyebrow="Three modes, one voice"
        title={<>Recorded, live, or <em>live as yourself</em></>}
        lede="Pick a mode to see what happens inside it. All three share the same voice profile and glossary."
      />
      <div data-reveal className="card mt-14 grid gap-2 p-2 lg:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)]">
        <ul className="flex flex-col gap-2">
          {MODES.map((x, i) => {
            const on = i === open;
            return (
              <li key={x.name} className={`relative overflow-hidden rounded-[18px] border transition-colors duration-300 ${on ? "flex-1 border-line bg-bg" : "border-transparent hover:bg-sunken"}`}>
                {on && <span aria-hidden className="absolute inset-y-0 left-0 w-1" style={{ background: x.hue }} />}
                <h3>
                  <button type="button" aria-expanded={on} aria-controls={`mode-${x.name}`} onClick={() => setOpen(i)} className="flex w-full items-center gap-4 p-5 text-left sm:px-7">
                    <span className={`grid size-11 shrink-0 place-items-center rounded-[14px] border transition-colors ${on ? "border-fg bg-fg text-on-fg" : "border-line bg-surface"}`}>
                      <x.icon aria-hidden className="size-5" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="eyebrow flex items-center gap-2">
                        <span className="tnum">{x.no}</span>
                        <span aria-hidden className="h-px w-5 bg-line" />
                        {x.name}
                      </span>
                      <span className="mt-1 block text-lg font-medium tracking-[-0.01em]">{x.tag}</span>
                    </span>
                    <ArrowRight aria-hidden className={`size-4 shrink-0 transition-transform duration-300 ${on ? "rotate-90" : "text-muted"}`} />
                  </button>
                </h3>
                {on && (
                  <div id={`mode-${x.name}`} className="rise px-5 pb-6 sm:px-7" style={{ animationDuration: "0.4s" }}>
                    <p className="h-display text-[1.7rem] leading-[1.08] sm:text-[2rem]">{x.title}</p>
                    <p className="mt-3 text-muted">{x.text}</p>
                    <ul className="mt-4 space-y-2">
                      {x.points.map((pt) => (
                        <li key={pt} className="flex items-start gap-2.5">
                          <Check aria-hidden className="mt-1 size-4 shrink-0 text-ok" />
                          {pt}
                        </li>
                      ))}
                    </ul>
                    <LinkButton href={x.href} className="mt-6">
                      {x.cta}
                      <ArrowRight aria-hidden className="size-4 transition-transform group-hover:translate-x-0.5" />
                    </LinkButton>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
        <div className="flex min-w-0 flex-col gap-2">
          <div key={m.name} className="rise" style={{ animationDuration: "0.45s" }}>
            {m.mock}
          </div>
          <Flow steps={m.steps} hue={m.hue} />
        </div>
      </div>
      <p className="mt-4 text-sm text-muted">The player and the steps above are illustrations of each mode. Your own reel and stream appear in them once dubbed.</p>
    </section>
  );
}
