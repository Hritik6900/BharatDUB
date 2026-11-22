"use client";
import { useEffect, useState } from "react";
import { Check } from "lucide-react";
import { api } from "@/lib/api";

export type Quality = "standard" | "hq";

const OPTIONS: [Quality, string, string][] = [
  ["standard", "Standard", "One voice take per line. Ready in about the length of the video."],
  ["hq", "HQ", "Every line is checked after it is spoken; a line that fails gets more takes and the best one is kept. Lines that still fail are marked for you. Takes several times longer."],
];

/**
 * Standard or HQ dubbing for one job. Renders nothing unless the server says the HQ path is switched on, so a
 * setup without it looks exactly as before. The choice starts on Standard.
 */
export function QualityPicker({ value, onChange }: { value: Quality; onChange: (q: Quality) => void }) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    api<Record<string, boolean | string>>("/api/v1/flags")
      .then((f) => setReady(f.V1_STUDIO_HQ === true))
      .catch(() => setReady(false));
  }, []);
  if (!ready) return null;
  return (
    <fieldset>
      <legend className="text-lg font-medium tracking-[-0.01em]">
        Quality <span className="text-sm font-normal text-muted">new</span>
      </legend>
      <div className="mt-3 grid gap-2.5 sm:grid-cols-2" role="radiogroup" aria-label="Quality">
        {OPTIONS.map(([v, label, hint]) => (
          <button key={v} type="button" role="radio" aria-checked={value === v} onClick={() => onChange(v)}
            className={`rounded-panel border p-4 text-left transition-colors ${value === v ? "border-fg bg-sunken" : "border-line hover:border-fg/50"}`}>
            <span className="flex items-center justify-between gap-2 font-medium">
              {label}
              <span className={`grid size-5 shrink-0 place-items-center rounded-full border ${value === v ? "border-fg bg-fg text-on-fg" : "border-line"}`}>
                {value === v && <Check aria-hidden className="size-3" />}
              </span>
            </span>
            <span className="mt-1 block text-sm text-muted">{hint}</span>
          </button>
        ))}
      </div>
    </fieldset>
  );
}
