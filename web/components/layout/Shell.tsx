import type { ReactNode } from "react";
import { Footer } from "./Footer";
import { Header } from "./Header";
import { SmoothScroll } from "./SmoothScroll";

interface Props {
  children: ReactNode;
  dark?: boolean;
  aura?: "full" | "soft" | "none";
  footer?: boolean;
}

/** Page frame: aura, sticky header, content, footer, smooth scrolling. */
export function Shell({ children, dark = false, aura = "soft", footer = true }: Props) {
  return (
    <div className={`relative flex min-h-dvh flex-col bg-bg text-fg ${dark ? "theme-dark" : ""}`}>
      <SmoothScroll />
      {aura !== "none" && <div aria-hidden className={`aura ${aura === "soft" ? "aura-sm" : ""}`} />}
      <Header />
      <main className="relative z-10 flex-1">{children}</main>
      {footer && <Footer />}
    </div>
  );
}
