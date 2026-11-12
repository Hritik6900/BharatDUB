"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ServerNotice } from "@/components/ui/ServerNotice";

const LINKS = [
  { href: "/studio", label: "Studio" },
  { href: "/live", label: "Live" },
  { href: "/voices", label: "Voices" },
  { href: "/glossary", label: "Glossary" },
  { href: "/dashboard", label: "Dashboard" },
];

export function Wordmark() {
  return (
    <Link href="/" className="font-display text-[1.35rem] font-semibold leading-none" style={{ fontVariationSettings: '"wdth" 112' }}>
      Bharat{" "}
      <span className="relative inline-block">
        Dub
        <span aria-hidden className="absolute -bottom-1.5 left-0 h-[3px] w-full rounded-chip" style={{ background: "linear-gradient(90deg,var(--hi),var(--ta))" }} />
      </span>
    </Link>
  );
}

export function Nav() {
  const path = usePathname();
  return (
    <header className="sticky top-0 z-40 border-b border-mist bg-bg/90 backdrop-blur">
      <ServerNotice />
      <nav aria-label="Main" className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-8">
        <span className="shrink-0">
          <Wordmark />
        </span>
        <ul className="flex min-w-0 items-center gap-1 overflow-x-auto font-display text-[0.95rem] [scrollbar-width:none]">
          {LINKS.map((l) => {
            const active = path?.startsWith(l.href);
            return (
              <li key={l.href}>
                <Link
                  href={l.href}
                  aria-current={active ? "page" : undefined}
                  className={`block rounded-chip px-3 py-1.5 ${active ? "bg-fg text-on-fg" : "text-slate hover:text-fg"} ${
                    l.href === "/glossary" ? "hidden md:block" : ""
                  }`}
                >
                  {l.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </header>
  );
}
