import type { ReactNode } from "react";
import { ArrowRight, Radio, ShieldCheck, Tag, Trash2 } from "lucide-react";
import { LinkButton } from "@/components/ui/Button";
import { VoiceOrb } from "@/components/voice/VoiceOrb";
import { HEADLINE, LANGS } from "@/lib/langs";

export function SectionHead({ eyebrow, title, lede, center = false }: { eyebrow: string; title: ReactNode; lede?: ReactNode; center?: boolean }) {
  return (
    <div data-reveal className={center ? "mx-auto max-w-3xl text-center" : "max-w-3xl"}>
      <p className="eyebrow">{eyebrow}</p>
      <h2 className="h-display mt-4 text-[clamp(2.4rem,5.5vw,4.25rem)]">{title}</h2>
      {lede && <p className={`mt-5 max-w-[56ch] text-[1.08rem] text-muted ${center ? "mx-auto" : ""}`}>{lede}</p>}
    </div>
  );
}

/** The headline, in every script we dub, scrolling by. */
export function ScriptMarquee() {
  const row = (hidden: boolean) => (
    <ul aria-hidden={hidden || undefined} className="flex shrink-0 items-center">
      {LANGS.map((l) => (
        <li key={l.code} lang={l.short} className="flex items-center gap-10 pr-10 font-indic text-[clamp(1.5rem,3.4vw,2.4rem)] font-medium text-fg/75">
          {HEADLINE[l.code]}
          <span aria-hidden className="size-2.5 rounded-full" style={{ background: l.hue }} />
        </li>
      ))}
    </ul>
  );
  return (
    <section aria-label="One line in five scripts" className="border-y border-line py-7">
      <div className="marquee">
        <div className="marquee-track">
          {row(false)}
          {row(true)}
        </div>
      </div>
    </section>
  );
}

const PROMISES = [
  { icon: ShieldCheck, title: "Consent comes first", text: "Your voice is copied only after you read a consent sentence aloud in the recording. No consent, no clone. You can delete it in one click." },
  { icon: Tag, title: "Always labelled", text: "Every dubbed video carries “AI-dubbed by Bharat Dub” in the player and as the first subtitle, so viewers know what they are hearing." },
  { icon: Trash2, title: "Uploads do not linger", text: "Videos you upload are deleted after 24 hours. Live audio is never stored at all." },
];

export function Trust() {
  return (
    <section className="mx-auto max-w-6xl px-5 py-24 sm:px-8 sm:py-32">
      <SectionHead eyebrow="Trust" title={<>Your voice stays <em>yours.</em></>} lede="A copy of someone's voice is a serious thing. These three rules are built into the product, not written in a policy." />
      <ul className="mt-14 grid gap-5 md:grid-cols-3">
        {PROMISES.map((p) => (
          <li key={p.title} data-reveal className="card p-7">
            <span className="grid size-12 place-items-center rounded-[14px] border border-line bg-bg">
              <p.icon aria-hidden className="size-5" />
            </span>
            <h3 className="mt-6 text-xl font-medium tracking-[-0.01em]">{p.title}</h3>
            <p className="mt-2.5 text-muted">{p.text}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function FinalCTA() {
  return (
    <section className="px-3 pb-24 sm:px-5 sm:pb-32">
      <div data-reveal className="card relative mx-auto max-w-6xl overflow-hidden px-6 py-20 text-center sm:py-28">
        <div aria-hidden className="pointer-events-none absolute left-1/2 top-full -translate-x-1/2 -translate-y-1/2 opacity-70">
          <VoiceOrb size={620} />
        </div>
        <div className="relative">
          <h2 className="h-display text-[clamp(2.8rem,7.5vw,6rem)] leading-[0.95]">
            Speak once.
            <br />
            <em>Be heard everywhere.</em>
          </h2>
          <p className="mx-auto mt-6 max-w-[46ch] text-[1.08rem] text-muted">Start with a reel you have already made, or open a live session before your next stream.</p>
          <div className="mt-9 flex flex-wrap justify-center gap-3">
            <LinkButton href="/studio" size="lg">
              Dub a video
              <ArrowRight aria-hidden className="size-4 transition-transform group-hover:translate-x-0.5" />
            </LinkButton>
            <LinkButton href="/live" size="lg" variant="secondary">
              <Radio aria-hidden className="size-4" />
              Go live
            </LinkButton>
          </div>
        </div>
      </div>
    </section>
  );
}
