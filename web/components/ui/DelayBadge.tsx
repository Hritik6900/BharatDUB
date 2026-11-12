/** "Dub delay 3.6 s": only rendered from a measured value. */
export function DelayBadge({ ms, large = false, label = "Dub delay" }: { ms: number | null | undefined; large?: boolean; label?: string }) {
  if (ms == null) return null;
  return (
    <span
      className={`inline-flex items-baseline gap-2 rounded-chip border border-mist bg-surface font-display ${
        large ? "px-6 py-3 text-2xl" : "px-3 py-1 text-sm"
      }`}
      aria-live="polite"
    >
      <span className="text-slate">{label}</span>
      <span className="tnum font-semibold">{(ms / 1000).toFixed(1)} s</span>
    </span>
  );
}
