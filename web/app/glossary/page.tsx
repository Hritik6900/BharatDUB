"use client";
import { useEffect, useState } from "react";
import { BookA, Lock, Plus, X } from "lucide-react";
import { Shell } from "@/components/layout/Shell";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
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
    <Shell>
      <div className="mx-auto max-w-4xl px-5 pb-24 pt-12 sm:px-8 sm:pt-16">
        <PageHeader
          icon={BookA}
          eyebrow="Glossary"
          title={<>Words that <em>stay</em></>}
          lede="Words that are never translated: your name, game titles, brand names, catchphrases. They also help speech recognition spell them right."
        />

        <form onSubmit={add} className="card card-lift rise mt-12 grid gap-3 p-4 sm:grid-cols-[1fr_1.4fr_auto] sm:p-5">
          <input required value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Word, e.g. Valorant" aria-label="Word" className="input" />
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note (optional)" aria-label="Note" className="input" />
          <Button type="submit" size="lg" className="h-12" disabled={!term.trim()}>
            <Plus aria-hidden className="size-4" />
            Add
          </Button>
        </form>
        {err && <div className="mt-4"><Notice tone="error" role="alert">{err}</Notice></div>}

        <section className="rise mt-12" aria-labelledby="mine-h" style={{ animationDelay: "0.08s" }}>
          <h2 id="mine-h" className="eyebrow">Your words <span className="tnum ml-1">{terms.length}</span></h2>
          {terms.length ? (
            <ul className="mt-4 flex flex-wrap gap-2.5">
              {terms.map((t) => (
                <li key={t.id} className="inline-flex items-center gap-2 rounded-chip border border-line bg-surface py-1.5 pl-4 pr-1.5">
                  <span className="font-medium">{t.term}</span>
                  {t.note && <span className="text-sm text-muted">{t.note}</span>}
                  <button
                    onClick={async () => {
                      await api(`/api/glossary/${t.id}`, { method: "DELETE" });
                      load();
                    }}
                    className="grid size-7 place-items-center rounded-full text-muted transition-colors hover:bg-sunken hover:text-danger"
                    aria-label={`Remove ${t.term}`}
                  >
                    <X aria-hidden className="size-4" />
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-4 text-muted">No words of your own yet. Add the first one above.</p>
          )}
        </section>

        {defaults.length > 0 && (
          <section className="rise mt-12" aria-labelledby="def-h" style={{ animationDelay: "0.14s" }}>
            <h2 id="def-h" className="eyebrow flex items-center gap-2">
              <Lock aria-hidden className="size-3.5" />
              Always kept
            </h2>
            <ul className="mt-4 flex flex-wrap gap-2">
              {defaults.map((d) => (
                <li key={d} className="rounded-chip bg-sunken px-3.5 py-1.5 text-sm">{d}</li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </Shell>
  );
}
