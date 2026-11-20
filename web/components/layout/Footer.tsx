import Link from "next/link";
import { ArrowUpRight, ShieldCheck, Tag, Trash2 } from "lucide-react";
import { Wordmark } from "./Logo";

const COLS = [
  {
    title: "Products",
    links: [
      { href: "/studio", label: "Studio" },
      { href: "/streamer", label: "Streamer" },
      { href: "/live", label: "Any stream" },
      { href: "/#how", label: "How it works" },
    ],
  },
  {
    title: "Your account",
    links: [
      { href: "/voices", label: "Your voice" },
      { href: "/glossary", label: "Glossary" },
      { href: "/dashboard", label: "Dashboard" },
    ],
  },
];
const PROMISES = [
  { icon: ShieldCheck, text: "Voices cloned only with recorded consent" },
  { icon: Tag, text: "Every dub labelled as AI-dubbed" },
  { icon: Trash2, text: "Uploads deleted after 24 hours" },
];

export function Footer() {
  return (
    <footer className="theme-dark relative z-10 overflow-hidden rounded-t-[32px] border-t border-line bg-bg text-fg">
      <div className="mx-auto max-w-6xl px-5 pt-16 sm:px-8 sm:pt-20">
        <div className="grid gap-12 md:grid-cols-[1.5fr_1fr_1fr_1.4fr]">
          <div>
            <Wordmark />
            <p className="mt-5 max-w-[34ch] text-muted">One voice, every Indian language. For creators and streamers.</p>
            <ul className="mt-7 space-y-2.5 text-sm">
              {PROMISES.map((p) => (
                <li key={p.text} className="flex items-center gap-2.5">
                  <p.icon aria-hidden className="size-4 text-muted" />
                  {p.text}
                </li>
              ))}
            </ul>
          </div>
          {COLS.map((c) => (
            <nav key={c.title} aria-label={c.title}>
              <h2 className="eyebrow">{c.title}</h2>
              <ul className="mt-5 space-y-3">
                {c.links.map((l) => (
                  <li key={l.href}>
                    <Link href={l.href} className="group inline-flex items-center gap-1 text-fg/90 hover:text-fg">
                      {l.label}
                      <ArrowUpRight aria-hidden className="size-3.5 opacity-0 transition-opacity group-hover:opacity-100" />
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
          <div>
            <h2 className="eyebrow">Built with</h2>
            <p className="mt-5 text-sm leading-relaxed text-muted">
              Models: IndicF5 by AI4Bharat, Demucs, Silero VAD, Gnani AI speech models and Gemini. Open source: FastAPI, Next.js, GSAP, Lenis,
              Lucide, and the Outfit, Instrument Serif, Geist Mono, Anek and Noto typefaces.
            </p>
          </div>
        </div>

        <p aria-hidden className="text-spectrum mt-16 select-none whitespace-nowrap text-center font-display text-[clamp(3rem,16vw,14rem)] font-semibold leading-[0.9] tracking-[-0.06em] opacity-90">
          Bharat Dub
        </p>
      </div>
      <div className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-5 py-5 text-sm text-muted sm:px-8">
          <p>© 2026 Bharat Dub. Made in India.</p>
          <p className="font-indic">हिन्दी · தமிழ் · বাংলা · తెలుగు · English</p>
        </div>
      </div>
    </footer>
  );
}
