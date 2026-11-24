"use client";
import { useCallback, useEffect, useState } from "react";
import { Headphones, SkipForward } from "lucide-react";
import { Shell } from "@/components/layout/Shell";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { API_BASE, ApiError, api } from "@/lib/api";
import { lang } from "@/lib/langs";

// A pair as this page gets it: two sounds, "first" and "second". Never which system made which.
interface Pair {
  id: string;
  lang: string;
  text: string;
}
interface Queue {
  name: string;
  total: number;
  done: number;
  pairs: Pair[];
}
type Prefer = "1" | "2" | "same";

const KEY = "bd-listener";
const SCALE: [number, string][] = [[1, "bad"], [2, "poor"], [3, "fair"], [4, "good"], [5, "excellent"]];

/** A random id kept in this browser: it only keeps one listener's answers together and decides their order. */
function listenerId(): string {
  try {
    const had = localStorage.getItem(KEY);
    if (had && /^[A-Za-z0-9_-]{8,64}$/.test(had)) return had;
    const made = Array.from(crypto.getRandomValues(new Uint8Array(12)), (b) => b.toString(16).padStart(2, "0")).join("");
    localStorage.setItem(KEY, made);
    return made;
  } catch {
    return `tmp${Math.random().toString(36).slice(2, 12)}`;
  }
}

function Rating({ name, value, onChange }: { name: string; value: number; onChange: (n: number) => void }) {
  return (
    <fieldset className="mt-3">
      <legend className="text-sm text-muted">How good does it sound?</legend>
      <div className="mt-2 flex flex-wrap gap-2" role="radiogroup" aria-label={`Rating for the ${name} clip`}>
        {SCALE.map(([n, word]) => (
          <button key={n} type="button" role="radio" aria-checked={value === n} onClick={() => onChange(n)}
            className={`rounded-chip border px-3 py-1.5 text-sm transition-colors ${value === n ? "border-fg bg-fg text-on-fg" : "border-line bg-surface hover:border-fg/50"}`}>
            <span className="tnum font-mono font-semibold">{n}</span> <span className={value === n ? "" : "text-muted"}>{word}</span>
          </button>
        ))}
      </div>
    </fieldset>
  );
}

export default function ListenTestPage() {
  const [who, setWho] = useState("");
  const [queue, setQueue] = useState<Pair[]>([]);
  const [meta, setMeta] = useState<Omit<Queue, "pairs"> | null>(null);
  const [r1, setR1] = useState(0);
  const [r2, setR2] = useState(0);
  const [prefer, setPrefer] = useState<Prefer | "">("");
  const [err, setErr] = useState("");
  const [off, setOff] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (id: string) => {
    try {
      const q = await api<Queue>(`/api/v1/listen/pairs?listener=${id}`);
      setQueue(q.pairs);
      setMeta({ name: q.name, total: q.total, done: q.done });
      setErr("");
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) setOff(true);
      else setErr((e as Error).message);
    }
  }, []);
  useEffect(() => {
    const id = listenerId();
    setWho(id);
    void load(id);
  }, [load]);

  const pair = queue[0];
  const reset = () => {
    setR1(0);
    setR2(0);
    setPrefer("");
  };
  const next = () => {
    reset();
    if (queue.length > 1) setQueue(queue.slice(1));
    else void load(who);
  };
  const send = async () => {
    if (!pair || !r1 || !r2 || !prefer || busy) return;
    setBusy(true);
    try {
      await api("/api/v1/listen/answers", { method: "POST", body: JSON.stringify({ listener: who, pair: pair.id, rating_1: r1, rating_2: r2, prefer }) });
      setMeta((m) => (m ? { ...m, done: m.done + 1 } : m));
      next();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const src = (side: "1" | "2") => `${API_BASE}/api/v1/listen/audio/${pair?.id}/${side}?listener=${who}`;
  const choices: [Prefer, string][] = [["1", "The first"], ["same", "No difference"], ["2", "The second"]];

  return (
    <Shell>
      <div className="mx-auto max-w-3xl px-5 pb-24 pt-12 sm:px-8 sm:pt-16">
        <PageHeader
          icon={Headphones}
          eyebrow="Listening test"
          title={<>Which one <em>sounds</em> better?</>}
          lede="Two clips say the same line. They come from two different voice systems and you are not told which is which; the order changes from pair to pair. Rate each one, then say which you would rather hear."
        />
        {off && (
          <div className="mt-8">
            <Notice tone="warn">This page is switched off. Set V1_LISTEN_TEST=true in the backend&apos;s settings and restart it.</Notice>
          </div>
        )}
        {err && <div className="mt-8"><Notice tone="error" role="alert">{err}</Notice></div>}

        {!off && meta && (
          <section className="card rise mt-8 p-6" aria-label="Pair to rate">
            <h2 className="eyebrow">
              {meta.done} of {meta.total} pairs answered{meta.name ? ` · ${meta.name}` : ""}
            </h2>
            {meta.total === 0 ? (
              <p className="mt-4 text-muted">There are no pairs yet. They are put into the server&apos;s data folder (docs/v1/RUNBOOK.md, &quot;Listening test&quot;).</p>
            ) : !pair ? (
              <p className="mt-4 text-muted">You have answered every pair. Thank you.</p>
            ) : (
              <>
                {pair.text && (
                  <>
                    <p className="mt-5 text-sm text-muted">{pair.lang ? `${lang(pair.lang).name}: both` : "Both"} clips should say</p>
                    <p className="mt-1 text-xl leading-relaxed" lang={pair.lang ? pair.lang.slice(0, 2) : undefined}>{pair.text}</p>
                  </>
                )}
                {/* key: new elements per pair, so an old clip never plays under a new line */}
                <div key={pair.id} className="mt-6 grid gap-6 sm:grid-cols-2">
                  <div>
                    <h3 className="font-medium">First clip</h3>
                    <audio className="mt-2 w-full" controls preload="auto" src={src("1")} />
                    <Rating name="first" value={r1} onChange={setR1} />
                  </div>
                  <div>
                    <h3 className="font-medium">Second clip</h3>
                    <audio className="mt-2 w-full" controls preload="auto" src={src("2")} />
                    <Rating name="second" value={r2} onChange={setR2} />
                  </div>
                </div>
                <fieldset className="mt-7">
                  <legend className="font-medium">Which would you rather hear?</legend>
                  <div className="mt-2 flex flex-wrap gap-2" role="radiogroup" aria-label="Preference">
                    {choices.map(([v, label]) => (
                      <button key={v} type="button" role="radio" aria-checked={prefer === v} onClick={() => setPrefer(v)}
                        className={`rounded-chip border px-4 py-2 text-sm font-medium transition-colors ${prefer === v ? "border-fg bg-fg text-on-fg" : "border-line bg-surface hover:border-fg/50"}`}>
                        {label}
                      </button>
                    ))}
                  </div>
                </fieldset>
                <div className="mt-7 flex flex-wrap items-center gap-4">
                  <Button disabled={!r1 || !r2 || !prefer || busy} onClick={() => void send()}>
                    {busy ? "Saving…" : "Save and go on"}
                  </Button>
                  <button type="button" onClick={next} className="inline-flex items-center gap-2 rounded-chip px-3 py-2 text-sm text-muted hover:bg-fg/5">
                    <SkipForward aria-hidden className="size-4" /> Skip this pair
                  </button>
                  {(!r1 || !r2 || !prefer) && <span className="text-sm text-muted">Listen to both, rate both and choose.</span>}
                </div>
              </>
            )}
          </section>
        )}
        {!off && (
          <p className="mt-5 text-xs text-muted">
            Your answers are kept on this server under a random id made by this browser, with no name. Use headphones if you can. The results are on the Numbers page.
          </p>
        )}
      </div>
    </Shell>
  );
}
