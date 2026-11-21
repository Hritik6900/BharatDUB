"use client";
import { useEffect, useState } from "react";
import { Check } from "lucide-react";
import { api } from "@/lib/api";

export type Engine = "cloud" | "gpu";

const OPTIONS: [Engine, string, string][] = [
  ["cloud", "Standard", "Hosted speech recognition and translation. The way Bharat Dub has always worked."],
  ["gpu", "GPU engine", "Speech recognition and translation run on our own GPU beside the voice. Hindi and Hinglish speech only."],
];

/**
 * Standard (hosted services) or our own GPU engine, for one session or one job. Renders nothing unless the server
 * says the GPU engine is set up, so a setup without it looks exactly as before. The choice starts on Standard.
 */
export function EnginePicker({ value, onChange }: { value: Engine; onChange: (e: Engine) => void }) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    api<{ gpu_mode?: boolean }>("/api/streamers/health")
      .then((h) => setReady(Boolean(h.gpu_mode)))
      .catch(() => setReady(false));
  }, []);
  if (!ready) return null;
  return (
    <fieldset>
      <legend className="text-lg font-medium tracking-[-0.01em]">
        Engine <span className="text-sm font-normal text-muted">new</span>
      </legend>
      <div className="mt-3 grid gap-2.5 sm:grid-cols-2" role="radiogroup" aria-label="Engine">
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
