"use client";
import type { ReactNode } from "react";
import { lang } from "@/lib/langs";

interface Props {
  code: string;
  selected?: boolean;
  onClick?: () => void;
  size?: "md" | "lg";
  showNative?: boolean;
  role?: "checkbox" | "radio" | "tab";
  children?: ReactNode;
  onHover?: () => void;
}

/** A language, in its own hue and its own script. */
export function LanguageChip({ code, selected = false, onClick, size = "md", showNative = true, role = "checkbox", children, onHover }: Props) {
  const l = lang(code);
  const pad = size === "lg" ? "h-14 px-6 text-[1.15rem]" : "h-10 px-4 text-[0.95rem]";
  return (
    <button
      type="button"
      role={role}
      aria-checked={role !== "tab" ? selected : undefined}
      aria-selected={role === "tab" ? selected : undefined}
      onClick={onClick}
      onMouseEnter={onHover}
      onFocus={onHover}
      style={{ ["--hue" as string]: l.hue }}
      className={`inline-flex items-center gap-2.5 rounded-chip border font-display transition-colors ${pad} ${
        selected ? "border-[var(--hue)] bg-[var(--hue)] text-white" : "border-mist bg-surface text-fg hover:border-[var(--hue)]"
      }`}
    >
      <span aria-hidden className={`size-2.5 rounded-full ${selected ? "bg-white" : "bg-[var(--hue)]"}`} />
      <span>{showNative && l.native !== l.name ? `${l.native}` : l.name}</span>
      {showNative && l.native !== l.name && <span className={selected ? "text-white/80" : "text-slate"}>{l.name}</span>}
      {children}
    </button>
  );
}
