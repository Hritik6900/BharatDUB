import Link from "next/link";

// M0 landing: two modes. The full hero (voice morph, pipeline story) comes with FRONTEND.md section 3.
const modes = [
  {
    href: "/studio",
    title: "Studio",
    line: "Upload your reel or short. Get it back in Tamil, Bengali, Telugu or English, in your own voice.",
    cta: "Dub a video",
    to: "var(--ta)",
  },
  {
    href: "/live",
    title: "Live",
    line: "Stream in Hindi. Your viewers pick a language and hear you dubbed a few seconds behind.",
    cta: "Go live",
    to: "var(--bn)",
  },
];

export default function Home() {
  return (
    <main className="mx-auto max-w-6xl px-4 py-[clamp(80px,12vh,160px)] sm:px-8">
      <h1
        className="font-display text-[clamp(2.6rem,7vw,5.4rem)] font-semibold leading-[1.05]"
        style={{ fontVariationSettings: '"wdth" 112' }}
      >
        Ek awaaz. Har bhasha.
      </h1>
      <div className="voice-ribbon mt-6 h-1 w-full max-w-xl rounded-chip" aria-hidden />
      <p className="mt-6 max-w-[60ch] text-lg text-slate">
        Dub your videos, or your live stream, into Indian languages in your own voice.
      </p>

      <div className="mt-16 grid gap-6 md:grid-cols-2">
        {modes.map((m) => (
          <Link
            key={m.href}
            href={m.href}
            className="group block rounded-media border border-mist bg-white/60 p-8 transition-colors hover:border-fg"
          >
            <div
              className="voice-ribbon mb-8 h-24 rounded-panel opacity-90"
              style={{ ["--to" as string]: m.to }}
              aria-hidden
            />
            <h2 className="font-display text-3xl font-semibold">{m.title}</h2>
            <p className="mt-3 text-slate">{m.line}</p>
            <span className="mt-6 inline-block rounded-chip bg-ink px-5 py-2.5 font-display text-porcelain">
              {m.cta}
            </span>
          </Link>
        ))}
      </div>

      <p className="mt-16 text-sm text-slate">
        Your voice is cloned only with your recorded consent, and you can delete it any time. AI-dubbed content is
        labelled.
      </p>
    </main>
  );
}
