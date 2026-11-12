import Link from "next/link";
import { Wordmark } from "./Nav";

export function Footer() {
  return (
    <footer className="border-t border-mist">
      <div className="mx-auto grid max-w-6xl gap-10 px-4 py-14 sm:px-8 md:grid-cols-[1.2fr_1fr_1fr]">
        <div>
          <Wordmark />
          <p className="mt-5 max-w-[42ch] text-sm text-slate">
            AI-dubbed content is labelled, in the video and in the subtitles. Uploads are deleted after 24 hours.
          </p>
        </div>
        <div>
          <h2 className="font-display text-base font-semibold">Product</h2>
          <ul className="mt-3 space-y-1.5 text-sm text-slate">
            <li><Link className="hover:text-fg" href="/studio">Studio</Link></li>
            <li><Link className="hover:text-fg" href="/live">Live</Link></li>
            <li><Link className="hover:text-fg" href="/voices">Your voice</Link></li>
            <li><Link className="hover:text-fg" href="/dashboard">Dashboard</Link></li>
          </ul>
        </div>
        <div>
          <h2 className="font-display text-base font-semibold">Built with</h2>
          <p className="mt-3 text-sm text-slate">
            Speech models by Gnani AI (Prisma, Timbre, Vachana voice cloning). Open source: Demucs, Silero VAD, FastAPI,
            Next.js, GSAP, Lenis, Anek and Noto fonts.
          </p>
        </div>
      </div>
    </footer>
  );
}
