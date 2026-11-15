"use client";
import { useEffect, useRef, useState } from "react";
import { Check, Moon, Sun, SunMoon, type LucideIcon } from "lucide-react";

/** "auto": Studio, Streamer and Live are dark, the other pages light. "dark" / "light": the whole site. */
export type Theme = "auto" | "dark" | "light";
export const THEME_KEY = "bd-theme";

/** Runs before the first paint (see app/layout.tsx), so a chosen theme never flashes the other one. */
export const THEME_BOOT = `try{var t=localStorage.getItem("${THEME_KEY}");if(t==="dark"||t==="light")document.documentElement.dataset.theme=t}catch(e){}`;

const OPTIONS: { value: Theme; label: string; hint: string; icon: LucideIcon }[] = [
  { value: "auto", label: "Auto", hint: "Dark in Studio, Streamer and Live", icon: SunMoon },
  { value: "dark", label: "Dark", hint: "The whole site", icon: Moon },
  { value: "light", label: "Light", hint: "The whole site", icon: Sun },
];

export function ThemeSwitch({ inline = false }: { inline?: boolean }) {
  const [theme, setTheme] = useState<Theme>("auto");
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const t = document.documentElement.dataset.theme;
    if (t === "dark" || t === "light") setTheme(t);
  }, []);
  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("pointerdown", away);
    window.addEventListener("keydown", esc);
    return () => {
      window.removeEventListener("pointerdown", away);
      window.removeEventListener("keydown", esc);
    };
  }, [open]);

  const pick = (t: Theme) => {
    setTheme(t);
    setOpen(false);
    if (t === "auto") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = t;
    try {
      if (t === "auto") localStorage.removeItem(THEME_KEY);
      else localStorage.setItem(THEME_KEY, t);
    } catch {
      /* storage blocked: the choice lasts for this page only */
    }
  };
  const Now = OPTIONS.find((o) => o.value === theme)!.icon;
  if (inline) {
    // Inside the mobile menu: three buttons in a row, no pop-up.
    return (
      <div role="radiogroup" aria-label="Theme" className="flex gap-1 rounded-chip border border-line bg-bg p-1">
        {OPTIONS.map((o) => (
          <button key={o.value} type="button" role="radio" aria-checked={theme === o.value} title={o.hint} onClick={() => pick(o.value)}
            className={`inline-flex h-9 flex-1 items-center justify-center gap-2 rounded-chip px-3 text-sm font-medium transition-colors ${theme === o.value ? "bg-fg text-on-fg" : "text-muted hover:text-fg"}`}>
            <o.icon aria-hidden className="size-4" />
            {o.label}
          </button>
        ))}
      </div>
    );
  }
  return (
    <div ref={box} className="relative">
      <button
        type="button"
        aria-label={`Theme: ${theme}`}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="grid size-10 place-items-center rounded-chip border border-line bg-surface/70 backdrop-blur transition-colors hover:border-fg/50"
      >
        <Now aria-hidden className="size-[18px]" />
      </button>
      {open && (
        <ul role="menu" aria-label="Theme" className="card card-lift rise absolute right-0 top-full z-50 mt-2 w-64 p-1.5" style={{ animationDuration: "0.2s" }}>
          {OPTIONS.map((o) => (
            <li key={o.value} role="none">
              <button
                type="button"
                role="menuitemradio"
                aria-checked={theme === o.value}
                onClick={() => pick(o.value)}
                className={`flex w-full items-center gap-3 rounded-panel p-2.5 text-left transition-colors hover:bg-sunken ${theme === o.value ? "bg-sunken" : ""}`}
              >
                <span className="grid size-9 shrink-0 place-items-center rounded-[12px] border border-line bg-bg">
                  <o.icon aria-hidden className="size-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium">{o.label}</span>
                  <span className="block text-xs text-muted">{o.hint}</span>
                </span>
                {theme === o.value && <Check aria-hidden className="size-4 shrink-0" />}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
