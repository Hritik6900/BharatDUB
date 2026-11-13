import { CircleAlert, Info } from "lucide-react";
import type { ReactNode } from "react";

export function Notice({ tone = "info", children, role = "status" }: { tone?: "info" | "warn" | "error"; children: ReactNode; role?: "status" | "alert" }) {
  const hue = tone === "error" ? "var(--danger)" : tone === "warn" ? "var(--hi)" : "var(--muted)";
  const Icon = tone === "info" ? Info : CircleAlert;
  return (
    <p role={role} className="flex items-start gap-3 rounded-panel border bg-surface px-4 py-3 text-sm" style={{ borderColor: `color-mix(in oklab, ${hue} 55%, var(--line))` }}>
      <Icon aria-hidden className="mt-0.5 size-4 shrink-0" style={{ color: hue }} />
      <span className="min-w-0">{children}</span>
    </p>
  );
}
