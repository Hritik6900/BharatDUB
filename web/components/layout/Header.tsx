"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowRight, AudioLines, BookA, ChevronDown, Clapperboard, LayoutDashboard, Menu, Mic, Radio, X, type LucideIcon } from "lucide-react";
import { LinkButton } from "@/components/ui/Button";
import { useHealth } from "@/lib/hooks";
import { Wordmark } from "./Logo";

interface NavItem {
  href: string;
  label: string;
  desc: string;
  icon: LucideIcon;
}

const PRODUCTS: NavItem[] = [
  { href: "/studio", label: "Studio", desc: "Dub a reel or short, music kept", icon: Clapperboard },
  { href: "/streamer", label: "Streamer", desc: "Go live in your own voice", icon: Radio },
  { href: "/live", label: "Any stream (beta)", desc: "Dub a stream that is playing", icon: Radio },
];
const LINKS: NavItem[] = [
  { href: "/#how", label: "How it works", desc: "From your voice to a dubbed line", icon: AudioLines },
  { href: "/voices", label: "Your voice", desc: "Record once, with consent", icon: Mic },
  { href: "/glossary", label: "Glossary", desc: "Words that stay as they are", icon: BookA },
  { href: "/dashboard", label: "Dashboard", desc: "Measured numbers only", icon: LayoutDashboard },
];

/** Honest status line: backend down, or AI providers simulated (mock mode). */
function StatusBar() {
  const h = useHealth();
  if (h === null || (h !== "down" && !h.mock_providers)) return null;
  const down = h === "down";
  return (
    <div role="status" className="flex items-center justify-center gap-2 border-b border-line bg-surface px-4 py-1.5 text-center text-xs">
      <span aria-hidden className="size-1.5 shrink-0 rounded-full" style={{ background: down ? "var(--danger)" : "var(--hi)" }} />
      {down ? (
        <span>
          Backend not reachable. Start it with <code className="font-mono">uvicorn app.main:app</code>.
        </span>
      ) : (
        <span>
          Mock mode: speech, translation and voices are simulated
          <span className="hidden md:inline"> until the Gnani and LLM keys are added. Numbers shown come from the simulation</span>.
        </span>
      )}
    </div>
  );
}

export function Header() {
  const path = usePathname() ?? "";
  const [scrolled, setScrolled] = useState(false);
  const [menu, setMenu] = useState(false);
  const [products, setProducts] = useState(false);

  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 12);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  useEffect(() => {
    setMenu(false);
    setProducts(false);
  }, [path]);
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && (setMenu(false), setProducts(false));
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, []);

  const active = (href: string) => !href.includes("#") && path.startsWith(href);
  const link = (on: boolean) =>
    `inline-flex h-9 items-center gap-1 rounded-chip px-3.5 text-[0.93rem] transition-colors ${on ? "bg-sunken text-fg" : "text-muted hover:text-fg"}`;

  return (
    <header className="sticky top-0 z-40">
      <StatusBar />
      <div className="relative px-3 pt-3 sm:px-5">
        <nav
          aria-label="Main"
          className={`mx-auto flex h-14 max-w-6xl items-center justify-between gap-3 rounded-chip border pl-4 pr-2 transition-[background,border-color,box-shadow] duration-300 ${
            scrolled || menu ? "border-line bg-surface/85 shadow-card backdrop-blur-xl" : "border-transparent"
          }`}
        >
          <Wordmark />

          <ul className="hidden items-center gap-0.5 lg:flex">
            <li className="relative" onMouseEnter={() => setProducts(true)} onMouseLeave={() => setProducts(false)}>
              <button type="button" aria-expanded={products} aria-haspopup="true" onClick={() => setProducts((p) => !p)} className={link(active("/studio") || active("/live"))}>
                Products
                <ChevronDown aria-hidden className={`size-3.5 transition-transform ${products ? "rotate-180" : ""}`} />
              </button>
              {products && (
                <div className="absolute left-1/2 top-full w-[21rem] -translate-x-1/2 pt-3">
                  <ul className="card card-lift rise p-2" style={{ animationDuration: "0.25s" }}>
                    {PRODUCTS.map((p) => (
                      <li key={p.href}>
                        <Link href={p.href} className="flex items-center gap-3.5 rounded-panel p-3 hover:bg-sunken">
                          <span className="grid size-11 shrink-0 place-items-center rounded-[14px] border border-line bg-bg">
                            <p.icon aria-hidden className="size-5" />
                          </span>
                          <span>
                            <span className="block font-medium">{p.label}</span>
                            <span className="block text-sm text-muted">{p.desc}</span>
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </li>
            {LINKS.map((l) => (
              <li key={l.href}>
                <Link href={l.href} aria-current={active(l.href) ? "page" : undefined} className={link(active(l.href))}>
                  {l.label}
                </Link>
              </li>
            ))}
          </ul>

          <div className="flex items-center gap-1.5">
            <span className="hidden sm:block">
              <LinkButton href="/live" variant="ghost" size="sm">
                <Radio aria-hidden className="size-4" />
                Go live
              </LinkButton>
            </span>
            <LinkButton href="/studio" size="sm" className="h-10">
              Dub a video
              <ArrowRight aria-hidden className="size-4 transition-transform group-hover:translate-x-0.5" />
            </LinkButton>
            <button
              type="button"
              aria-label={menu ? "Close menu" : "Open menu"}
              aria-expanded={menu}
              onClick={() => setMenu((m) => !m)}
              className="grid size-10 place-items-center rounded-chip hover:bg-sunken lg:hidden"
            >
              {menu ? <X aria-hidden className="size-5" /> : <Menu aria-hidden className="size-5" />}
            </button>
          </div>
        </nav>

        {menu && (
          <div className="absolute inset-x-3 top-full mt-2 sm:inset-x-5 lg:hidden">
            <ul className="card card-lift rise mx-auto max-h-[75dvh] max-w-6xl overflow-y-auto p-2" style={{ animationDuration: "0.25s" }}>
              {[...PRODUCTS, ...LINKS].map((l) => (
                <li key={l.href}>
                  <Link href={l.href} onClick={() => setMenu(false)} className="flex items-center gap-3.5 rounded-panel p-3 hover:bg-sunken">
                    <span className="grid size-11 shrink-0 place-items-center rounded-[14px] border border-line bg-bg">
                      <l.icon aria-hidden className="size-5" />
                    </span>
                    <span>
                      <span className="block font-medium">{l.label}</span>
                      <span className="block text-sm text-muted">{l.desc}</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </header>
  );
}
