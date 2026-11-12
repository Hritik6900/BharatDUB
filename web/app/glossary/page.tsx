"use client";
import { useEffect, useState } from "react";
import { Nav } from "@/components/layout/Nav";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api";

interface Term {
  id: string;
  term: string;
  note?: string | null;
}

export default function GlossaryPage() {
  const [defaults, setDefaults] = useState<string[]>([]);
  const [terms, setTerms] = useState<Term[]>([]);
  const [term, setTerm] = useState("");
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  const load = () =>
    api<{ defaults: string[]; terms: Term[] }>("/api/glossary")
      .then((r) => {
        setDefaults(r.defaults);
        setTerms(r.terms);
      })
      .catch((e) => setErr((e as Error).message));
  useEffect(() => {
    load();
  }, []);
  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    try {
      await api("/api/glossary", { method: "POST", body: JSON.stringify({ term, note }) });
      setTerm("");
      setNote("");
      load();
    } catch (x) {
      setErr((x as Error).message);
    }
  };
  return (
    <>
      <Nav />
      <main className="mx-auto max-w-3xl px-4 py-12 sm:px-8 sm:py-16">
        <h1 className="font-display text-[clamp(2rem,5vw,3rem)] font-semibold leading-tight">Glossary</h1>
        <p className="mt-3 max-w-[60ch] text-slate">Words that are never translated: your name, game titles, brand names, catchphrases. They also help speech recognition spell them right.</p>
        <form onSubmit={add} className="mt-10 grid gap-3 sm:grid-cols-[1fr_1.4fr_auto]">
          <input required value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Word, e.g. Valorant" aria-label="Word" className="h-12 rounded-panel border border-mist bg-surface px-4" />
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note (optional)" aria-label="Note" className="h-12 rounded-panel border border-mist bg-surface px-4" />
          <Button type="submit" disabled={!term.trim()}>Add</Button>
        </form>
        {err && <p role="alert" className="mt-4 text-sm">{err}</p>}
        <ul className="mt-8 divide-y divide-mist border-y border-mist">
          {terms.map((t) => (
            <li key={t.id} className="flex items-center justify-between gap-4 py-3">
              <span>
                <span className="font-display font-semibold">{t.term}</span>
                {t.note && <span className="ml-3 text-sm text-slate">{t.note}</span>}
              </span>
              <button
                onClick={async () => {
                  await api(`/api/glossary/${t.id}`, { method: "DELETE" });
                  load();
                }}
                className="text-sm text-slate underline-offset-4 hover:text-fg hover:underline"
                aria-label={`Remove ${t.term}`}
              >
                Remove
              </button>
            </li>
          ))}
          {!terms.length && <li className="py-3 text-sm text-slate">No words of your own yet.</li>}
        </ul>
        <p className="mt-6 text-sm text-slate">Always kept: {defaults.join(", ")}</p>
      </main>
    </>
  );
}
