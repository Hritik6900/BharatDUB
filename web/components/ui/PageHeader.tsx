import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/** Top of every app page: small labelled eyebrow, serif title, one-line lede. */
export function PageHeader({ icon: Icon, eyebrow, title, lede, children }: { icon: LucideIcon; eyebrow: string; title: ReactNode; lede?: ReactNode; children?: ReactNode }) {
  return (
    <header className="rise flex flex-wrap items-end justify-between gap-6">
      <div>
        <p className="eyebrow inline-flex items-center gap-2 rounded-chip border border-line bg-surface/70 px-3 py-1.5 backdrop-blur">
          <Icon aria-hidden className="size-3.5" />
          {eyebrow}
        </p>
        <h1 className="h-display mt-5 text-[clamp(2.6rem,6vw,4.25rem)]">{title}</h1>
        {lede && <p className="mt-4 max-w-[58ch] text-[1.05rem] text-muted">{lede}</p>}
      </div>
      {children}
    </header>
  );
}
