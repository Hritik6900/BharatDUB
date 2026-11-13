"use client";
import type { ReactNode } from "react";
import { Check } from "lucide-react";
import { lang } from "@/lib/langs";

interface Props {
  code: string;
  selected?: boolean;
  onClick?: () => void;
  size?: "md" | "lg";
  role?: "checkbox" | "radio" | "tab";
  children?: ReactNode;
}

/** A language in its own script, marked with its hue. Selected = ink fill, so text contrast never depends on the hue. */
export function LanguageChip({ code, selected = false, onClick, size = "md", role = "checkbox", children }: Props) {
  const l = lang(code);
  const pad = size === "lg" ? "h-14 px-6 text-lg" : "h-11 px-4 text-[0.95rem]";
  return (
    <button
      type="button"
      role={role}
      aria-checked={role !== "tab" ? selected : undefined}
      aria-selected={role === "tab" ? selected : undefined}
      onClick={onClick}
      className={`inline-flex items-center gap-2.5 rounded-chip border transition-colors ${pad} ${
        selected ? "border-fg bg-fg text-on-fg" : "border-line bg-surface text-fg hover:border-fg"
      }`}
    >
      <span aria-hidden className="size-2.5 rounded-full" style={{ background: l.hue }} />
      {/* Anek sits high on its line box next to Latin text; nudge it onto the shared baseline. */}
      <span className={`font-indic font-medium leading-none ${l.native !== l.name ? "translate-y-[0.12em]" : ""}`}>{l.native}</span>
      {l.native !== l.name && <span className={`leading-none ${selected ? "opacity-70" : "text-muted"}`}>{l.name}</span>}
      {selected && role === "checkbox" && <Check aria-hidden className="size-4" />}
      {children}
    </button>
  );
}
