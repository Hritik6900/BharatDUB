"use client";
import { useHealth } from "@/lib/hooks";

/** Honest status line: backend down, or AI providers simulated (mock mode). */
export function ServerNotice() {
  const h = useHealth();
  if (h === null) return null;
  if (h === "down")
    return (
      <div role="status" className="border-b border-mist bg-surface px-4 py-2 text-center text-sm text-slate">
        Backend not reachable at the configured API address. Start it with <code>uvicorn app.main:app</code>.
      </div>
    );
  if (h.mock_providers)
    return (
      <div role="status" className="border-b border-mist bg-surface px-4 py-2 text-center text-sm">
        Mock mode: speech, translation and voices are simulated until the Gnani and LLM keys are added. Numbers shown come
        from the simulation.
      </div>
    );
  return null;
}
