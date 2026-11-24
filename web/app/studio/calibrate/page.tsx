"use client";
import { useCallback, useEffect, useState } from "react";
import { Ear, SkipForward, ThumbsDown, ThumbsUp, Undo2 } from "lucide-react";
import { Shell } from "@/components/layout/Shell";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { API_BASE, ApiError, api } from "@/lib/api";
import { lang } from "@/lib/langs";

// A take as this page gets it: what it should say and its sound. Never its score.
interface Take {
  id: string;
  lang: string;
  text: string;
}
interface Queue {
  items: Take[];
  takes: number;
  labelled: number;
  langs: string[];
}
interface Agreement {
  threshold: number;
  labels: number;
  flagged_bad: number;
  flagged_good: number;
  passed_bad: number;
  passed_good: number;
  agreement_pct: number | null;
  balanced_pct: number | null;
}
interface Summary {
  rule: string;
  takes: number;
  labelled: number;
  used: number;
  left_out_other_rule: number;
  unlabelled: number;
  good: number;
  bad: number;
  threshold_in_use: number;
  at_threshold_in_use: Agreement | null;
  recommended: Partial<Agreement> & { threshold: number | null; why: string };
  by_lang: Record<string, Agreement>;
  note: string;
}

const pct = (x: number) => `${Math.round(x * 100)}%`;

function Counts({ a }: { a: Agreement }) {
  const rows: [string, number][] = [
    ["Flagged, and you said bad", a.flagged_bad],
    ["Flagged, but you said good", a.flagged_good],
    ["Not flagged, but you said bad", a.passed_bad],
    ["Not flagged, and you said good", a.passed_good],
  ];
  return (
    <ul className="mt-3 text-sm">
      {rows.map(([name, n]) => (
        <li key={name} className="flex justify-between border-t border-line py-2 first:border-t-0">
          <span className="text-muted">{name}</span>
          <span className="tnum font-mono">{n}</span>
        </li>
      ))}
    </ul>
  );
}

export default function CalibratePage() {
  const [queue, setQueue] = useState<Take[]>([]);
  const [meta, setMeta] = useState<Omit<Queue, "items"> | null>(null);
  const [sum, setSum] = useState<Summary | null>(null);
  const [only, setOnly] = useState("");
  const [last, setLast] = useState<Take | null>(null);
  const [err, setErr] = useState("");
  const [off, setOff] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (language: string) => {
    try {
      const q = await api<Queue>(`/api/v1/calibrate/next?n=10${language ? `&lang=${language}` : ""}`);
      setQueue(q.items);
      setMeta({ takes: q.takes, labelled: q.labelled, langs: q.langs });
      setSum(await api<Summary>("/api/v1/calibrate/summary"));
      setErr("");
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) setOff(true);
      else setErr((e as Error).message);
    }
  }, []);
  useEffect(() => {
    void load(only);
  }, [load, only]);

  const take = queue[0];
  const answer = useCallback(
    async (label: "good" | "bad" | "skip") => {
      if (!take || busy) return;
      setBusy(true);
      try {
        if (label !== "skip") {
          await api("/api/v1/calibrate/labels", { method: "POST", body: JSON.stringify({ id: take.id, label }) });
          setLast(take);
        }
        if (queue.length > 1) {
          setQueue(queue.slice(1));
          if (label !== "skip") setSum(await api<Summary>("/api/v1/calibrate/summary"));
        } else await load(only);
      } catch (e) {
        setErr((e as Error).message);
      } finally {
        setBusy(false);
      }
    },
    [take, busy, queue, load, only],
  );
  const undo = async () => {
    if (!last) return;
    try {
      await api("/api/v1/calibrate/labels", { method: "POST", body: JSON.stringify({ id: last.id, label: "undo" }) });
      setLast(null);
      await load(only);
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return;
      if (e.key === "g") void answer("good");
      if (e.key === "b") void answer("bad");
      if (e.key === "s") void answer("skip");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [answer]);

  const rec = sum?.recommended;
  return (
    <Shell>
      <div className="mx-auto max-w-3xl px-5 pb-24 pt-12 sm:px-8 sm:pt-16">
        <PageHeader
          icon={Ear}
          eyebrow="Studio HQ"
          title={<>Does the checker hear what <em>you</em> hear?</>}
          lede="Listen to a dubbed line and say whether every word is clear. You are not shown what the automatic check made of it. Your answers show how often the two agree, and where the line for flagging should be."
        />
        {off && (
          <div className="mt-8">
            <Notice tone="warn">This page is switched off. Set V1_HQ_CALIBRATE=true in the backend&apos;s settings and restart it.</Notice>
          </div>
        )}
        {err && <div className="mt-8"><Notice tone="error" role="alert">{err}</Notice></div>}

        {!off && meta && (
          <section className="card rise mt-8 p-6" aria-label="Line to label">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="eyebrow">
                {meta.labelled} of {meta.takes} takes labelled
              </h2>
              <label className="text-sm text-muted">
                Language{" "}
                <select value={only} onChange={(e) => setOnly(e.target.value)} className="ml-1 rounded-chip border border-line bg-surface px-2 py-1 text-fg">
                  <option value="">all</option>
                  {meta.langs.map((code) => (
                    <option key={code} value={code}>{lang(code).name}</option>
                  ))}
                </select>
              </label>
            </div>
            {meta.takes === 0 ? (
              <p className="mt-4 text-muted">There is nothing to label yet. Takes appear here after a Studio job has run in HQ.</p>
            ) : !take ? (
              <p className="mt-4 text-muted">Every take{only ? ` in ${lang(only).name}` : ""} has a label.</p>
            ) : (
              <>
                <p className="mt-5 text-sm text-muted">{lang(take.lang).name}: the line should say</p>
                <p className="mt-1 text-xl leading-relaxed" lang={take.lang.slice(0, 2)}>{take.text}</p>
                {/* key: a new element per take, so the old sound never plays under new words */}
                <audio key={take.id} className="mt-4 w-full" controls autoPlay src={`${API_BASE}/api/v1/calibrate/audio/${take.id}`} />
                <div className="mt-5 flex flex-wrap gap-3">
                  <button type="button" disabled={busy} onClick={() => void answer("good")} className="inline-flex items-center gap-2 rounded-chip border border-line bg-surface px-4 py-2 font-semibold hover:bg-fg/5 disabled:opacity-50">
                    <ThumbsUp aria-hidden className="size-4 text-ok" /> Good: every word is clear <kbd className="font-mono text-xs text-muted">g</kbd>
                  </button>
                  <button type="button" disabled={busy} onClick={() => void answer("bad")} className="inline-flex items-center gap-2 rounded-chip border border-line bg-surface px-4 py-2 font-semibold hover:bg-fg/5 disabled:opacity-50">
                    <ThumbsDown aria-hidden className="size-4 text-danger" /> Bad: a word is wrong or unclear <kbd className="font-mono text-xs text-muted">b</kbd>
                  </button>
                  <button type="button" disabled={busy} onClick={() => void answer("skip")} className="inline-flex items-center gap-2 rounded-chip border border-line bg-surface px-4 py-2 text-muted hover:bg-fg/5 disabled:opacity-50">
                    <SkipForward aria-hidden className="size-4" /> Skip <kbd className="font-mono text-xs">s</kbd>
                  </button>
                  {last && (
                    <button type="button" onClick={() => void undo()} className="inline-flex items-center gap-2 rounded-chip px-3 py-2 text-sm text-muted hover:bg-fg/5">
                      <Undo2 aria-hidden className="size-4" /> Undo my last answer
                    </button>
                  )}
                </div>
              </>
            )}
          </section>
        )}

        {!off && sum && (
          <section className="card rise mt-5 p-6" aria-label="Agreement">
            <h2 className="eyebrow">You and the checker</h2>
            {sum.labelled === 0 ? (
              <p className="mt-3 text-muted">No labels yet. Nothing can be said about the checker, and no flag line is recommended, until you have labelled some lines.</p>
            ) : (
              <>
                <p className="mt-3 text-sm text-muted">
                  {sum.used} labels counted: {sum.good} good, {sum.bad} bad.
                  {sum.left_out_other_rule > 0 && <> {sum.left_out_other_rule} more are on takes scored by an older rule and are left out.</>}
                </p>
                {sum.at_threshold_in_use && (
                  <>
                    <p className="mt-4">
                      <span className="tnum h-display text-4xl">{sum.at_threshold_in_use.agreement_pct}%</span>
                      <span className="ml-3 text-sm text-muted">agreement with the flag line in use ({pct(sum.threshold_in_use)} of words heard back)</span>
                    </p>
                    <Counts a={sum.at_threshold_in_use} />
                  </>
                )}
                <h3 className="eyebrow mt-6">Recommended flag line</h3>
                {rec && rec.threshold != null ? (
                  <>
                    <p className="mt-3">
                      <span className="tnum h-display text-4xl">{pct(rec.threshold)}</span>
                      <span className="ml-3 text-sm text-muted">
                        of words heard back; agreement with your labels there: {rec.agreement_pct}%. Set V1_HQ_BACKCHECK_MIN={rec.threshold} to use it.
                      </span>
                    </p>
                    <Counts a={rec as Agreement} />
                  </>
                ) : (
                  <p className="mt-3 text-muted">None yet: {rec?.why}.</p>
                )}
                {Object.keys(sum.by_lang).length > 1 && (
                  <>
                    <h3 className="eyebrow mt-6">By language, with the flag line in use</h3>
                    <ul className="mt-3 text-sm">
                      {Object.entries(sum.by_lang).map(([code, a]) => (
                        <li key={code} className="flex justify-between border-t border-line py-2 first:border-t-0">
                          <span>{lang(code).name}</span>
                          <span className="tnum font-mono text-muted">{a.labels} labels, {a.agreement_pct}% agreement</span>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </>
            )}
            <p className="mt-5 text-xs text-muted">Labels are kept on this server only. How the recommendation is worked out: docs/v1/CALIBRATION.md.</p>
          </section>
        )}
      </div>
    </Shell>
  );
}
