"use client";
import { useEffect, useState } from "react";
import { AudioLines, BookA, Check, CircleDashed, Clapperboard, Database, Ear, FastForward, Languages, LoaderCircle, Mic, Radio, Scissors, ShieldCheck, Timer, Trash2, type LucideIcon } from "lucide-react";
import { VoiceOrb } from "@/components/voice/VoiceOrb";
import { useHealth, useReducedMotion } from "@/lib/hooks";
import { EXTRA_LANGS } from "@/lib/langs";

const CHIPS = [
  { icon: ShieldCheck, label: "Consent" },
  { icon: BookA, label: "Glossary" },
  { icon: Trash2, label: "Delete any time" },
];
const USED = [
  { icon: Clapperboard, label: "Studio lines" },
  { icon: Radio, label: "Live audio" },
  { icon: AudioLines, label: "Stock voice fallback" },
  { icon: Languages, label: "Every target language" },
];
const ORBIT: { icon: LucideIcon; pos: string }[] = [
  { icon: Clapperboard, pos: "left-1/2 top-0 -translate-x-1/2 -translate-y-1/2" },
  { icon: Radio, pos: "right-0 top-1/2 translate-x-1/2 -translate-y-1/2" },
  { icon: BookA, pos: "bottom-0 left-1/2 -translate-x-1/2 translate-y-1/2" },
  { icon: ShieldCheck, pos: "left-0 top-1/2 -translate-x-1/2 -translate-y-1/2" },
];

function VoiceCard() {
  return (
    <article data-reveal className="card grid gap-8 overflow-hidden p-6 sm:p-8 md:grid-cols-[1.15fr_1fr] md:items-center lg:col-span-3">
      <div>
        <h3 className="h-display text-[1.6rem]">A voice profile that is yours</h3>
        <p className="mt-3 text-muted">Record 20 to 30 seconds once. Studio and Live then speak every language in your voice, not a narrator&apos;s.</p>
        <ul className="mt-6 flex flex-wrap gap-x-5 gap-y-3">
          {CHIPS.map((c) => (
            <li key={c.label} className="flex items-center gap-2.5 font-medium">
              <span className="grid size-9 place-items-center rounded-full bg-sunken">
                <c.icon aria-hidden className="size-4" />
              </span>
              {c.label}
            </li>
          ))}
        </ul>
        <p className="eyebrow mt-8">Used by</p>
        <ul className="mt-3 grid gap-2 sm:grid-cols-2">
          {USED.map((u) => (
            <li key={u.label} className="flex items-center gap-2.5 rounded-chip border border-line bg-surface px-3.5 py-2 text-sm">
              <u.icon aria-hidden className="size-4 text-muted" />
              {u.label}
            </li>
          ))}
        </ul>
      </div>
      <div aria-hidden className="relative mx-auto grid aspect-square w-full max-w-[280px] place-items-center">
        <span className="absolute inset-0 rounded-full border border-line" />
        <span className="absolute inset-[13%] rounded-full border border-dashed border-line" />
        <span className="absolute inset-[26%] rounded-full bg-sunken" />
        <div className="orbit absolute inset-0">
          {ORBIT.map((o, i) => (
            <span key={i} className={`absolute grid size-10 place-items-center rounded-[12px] border border-line bg-surface shadow-card ${o.pos}`}>
              <o.icon className="size-[18px]" />
            </span>
          ))}
        </div>
        <VoiceOrb size="38%" />
      </div>
    </article>
  );
}

/** Live status of this server's providers, straight from /health. */
function StackCard() {
  const h = useHealth();
  const rows = [
    { icon: Ear, name: "Prisma", role: "speech to text", key: "gnani" as const, ai: true },
    { icon: AudioLines, name: "Timbre and Vachana", role: "voice and cloning", key: "gnani" as const, ai: true },
    { icon: Languages, name: "Translation model", role: "Evon or a backup", key: "llm" as const, ai: true },
    { icon: Database, name: "Supabase", role: "storage", key: "supabase" as const, ai: false },
  ];
  const status = (key: "gnani" | "llm" | "supabase", ai: boolean) => {
    if (h === null) return { label: "Checking", tone: "wait" };
    if (h === "down") return { label: "Server offline", tone: "off" };
    if (ai && h.mock_providers) return { label: "Simulated", tone: "sim" };
    if (h.configured[key]) return { label: "Connected", tone: "ok" };
    return { label: key === "supabase" ? "Local files" : "Key not set", tone: "off" };
  };
  return (
    <article data-reveal className="card flex flex-col p-6 sm:p-8 lg:col-span-2">
      <ul className="space-y-2.5">
        {rows.map((r) => {
          const s = status(r.key, r.ai);
          return (
            <li key={r.name} className="flex items-center gap-3 rounded-panel border border-line bg-surface px-4 py-3">
              <span className="grid size-9 shrink-0 place-items-center rounded-full bg-sunken">
                <r.icon aria-hidden className="size-4" />
              </span>
              <span className="min-w-0 flex-1 leading-tight">
                <span className="block truncate font-medium">{r.name}</span>
                <span className="text-sm text-muted">{r.role}</span>
              </span>
              <span className={`flex shrink-0 items-center gap-1.5 text-sm ${s.tone === "ok" ? "text-ok" : "text-muted"}`}>
                {s.label}
                {s.tone === "ok" ? <Check className="size-4" aria-hidden /> : s.tone === "wait" ? <LoaderCircle className="size-4 animate-spin" aria-hidden /> : <CircleDashed className="size-4" aria-hidden />}
              </span>
            </li>
          );
        })}
      </ul>
      <h3 className="h-display mt-7 text-[1.6rem]">Built on Gnani speech models</h3>
      <p className="mt-2 text-muted">Prisma listens, Timbre and Vachana speak. The status above is read live from this server.</p>
    </article>
  );
}

const FIT = [
  { icon: Timer, title: "Fits its slot", text: "Most lines do. Nothing is changed." },
  { icon: FastForward, title: "A little too long", text: "Sped up, never past 1.35x." },
  { icon: Scissors, title: "Still too long", text: "Rewritten shorter, then voiced again." },
];

function FitCard() {
  const [step, setStep] = useState(0);
  const reduced = useReducedMotion();
  useEffect(() => {
    if (reduced) return;
    const id = setInterval(() => setStep((s) => (s + 1) % FIT.length), 2200);
    return () => clearInterval(id);
  }, [reduced]);
  return (
    <article data-reveal className="card flex flex-col p-6 sm:p-8 lg:col-span-2">
      <div className="flex items-center justify-between">
        <p className="eyebrow flex items-center gap-2">
          <Timer aria-hidden className="size-3.5" />
          Every line, checked
        </p>
        <span aria-hidden className="flex gap-1">
          {FIT.map((_, i) => (
            <span key={i} className={`h-1.5 rounded-full transition-all duration-500 ${i === step ? "w-4 bg-fg" : "w-1.5 bg-line"}`} />
          ))}
        </span>
      </div>
      <ol className="mt-5 space-y-2.5">
        {FIT.map((f, i) => (
          <li key={f.title} className={`flex items-center gap-3.5 rounded-panel border px-4 py-3 transition-colors duration-500 ${i === step ? "border-fg bg-surface" : "border-line bg-surface/60"}`}>
            <span className="grid size-9 shrink-0 place-items-center rounded-full bg-sunken">
              <f.icon aria-hidden className="size-4" />
            </span>
            <span className="flex-1 leading-tight">
              <span className="block font-medium">{f.title}</span>
              <span className="text-sm text-muted">{f.text}</span>
            </span>
            <span aria-hidden className={`grid size-5 place-items-center rounded-full border transition-colors duration-500 ${i === step ? "border-fg bg-fg text-on-fg" : "border-line"}`}>
              {i === step && <Check className="size-3" />}
            </span>
          </li>
        ))}
      </ol>
      <h3 className="h-display mt-7 text-[1.6rem]">Timed to your video</h3>
      <p className="mt-2 text-muted">A dubbed line has to end before your next one starts. Each line goes through this check.</p>
    </article>
  );
}

function NextCard() {
  return (
    <article data-reveal className="card p-6 sm:p-8 lg:col-span-3">
      <h3 className="h-display text-[1.9rem]">Five more, switched on</h3>
      <p className="mt-2 text-muted">Kannada, Malayalam, Marathi, Gujarati and Punjabi work in Studio and Live, next to the first five.</p>
      <ul className="cells mt-6 grid-cols-2 sm:grid-cols-3">
        {EXTRA_LANGS.map((l) => (
          <li key={l.code} className="tex-dots grid h-32 place-items-center text-center">
            <span className="bg-surface px-3 py-1">
              <span lang={l.short} className="block text-2xl font-medium">{l.native}</span>
              <span className="text-sm text-muted">{l.name}</span>
            </span>
          </li>
        ))}
        <li className="tex-hatch grid h-32 place-items-center text-center">
          <span className="flex items-center gap-2 bg-surface px-3 py-1 text-sm text-muted">
            <Mic aria-hidden className="size-4" />
            Your voice in each
          </span>
        </li>
      </ul>
    </article>
  );
}

export function Bento() {
  return (
    <section aria-label="More of what is inside" className="mx-auto max-w-6xl px-5 py-24 sm:px-8 sm:py-32">
      <div data-reveal className="max-w-3xl">
        <p className="eyebrow">Under the hood</p>
        <h2 className="h-display mt-4 text-[clamp(2.4rem,5.5vw,4.25rem)]">
          The parts that make it <em>sound right</em>
        </h2>
      </div>
      <div className="mt-14 grid grid-cols-1 gap-5 lg:grid-cols-5">
        <VoiceCard />
        <StackCard />
        <FitCard />
        <NextCard />
      </div>
    </section>
  );
}
