"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Nav } from "@/components/layout/Nav";
import { Button } from "@/components/ui/Button";
import { LanguageChip } from "@/components/ui/LanguageChip";
import { API_BASE, api, type Job, type VoiceProfile } from "@/lib/api";
import { TARGET_LANGS, lang } from "@/lib/langs";

const MAX_MB = 500;

export default function StudioPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [drag, setDrag] = useState(false);
  const [langs, setLangs] = useState<string[]>(["ta-IN"]);
  const [voices, setVoices] = useState<VoiceProfile[]>([]);
  const [voiceId, setVoiceId] = useState<string>("");
  const [owns, setOwns] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [jobs, setJobs] = useState<Job[]>([]);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api<VoiceProfile[]>("/api/voices").then(setVoices).catch(() => {});
    api<Job[]>("/api/jobs").then(setJobs).catch(() => {});
  }, []);

  const pick = (f: File | undefined) => {
    setError("");
    if (!f) return;
    if (!/\.(mp4|mov|webm|mkv|m4v)$/i.test(f.name)) return setError("Use an MP4, MOV or WebM video.");
    if (f.size > MAX_MB * 1024 * 1024) return setError(`That file is over ${MAX_MB} MB.`);
    setFile(f);
  };
  const toggle = (c: string) => setLangs((l) => (l.includes(c) ? l.filter((x) => x !== c) : [...l, c]));

  const submit = async () => {
    if (!file) return;
    setBusy(true);
    setError("");
    const fd = new FormData();
    fd.append("file", file);
    fd.append("target_langs", langs.join(","));
    fd.append("owns_video", String(owns));
    if (voiceId) fd.append("voice_profile_id", voiceId);
    try {
      const { job_id } = await api<{ job_id: string }>("/api/jobs", { method: "POST", body: fd });
      router.push(`/studio/${job_id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };

  return (
    <>
      <Nav />
      <main className="mx-auto max-w-3xl px-4 py-12 sm:px-8 sm:py-16">
        <h1 className="font-display text-[clamp(2rem,5vw,3rem)] font-semibold leading-tight">Dub a video</h1>
        <p className="mt-3 text-slate">A reel, short or clip up to 3 minutes. You get an MP4 and subtitles for each language.</p>

        <div
          role="button"
          tabIndex={0}
          aria-label={file ? `Selected ${file.name}. Choose a different video` : "Choose a video, or drop it here"}
          onClick={() => input.current?.click()}
          onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            pick(e.dataTransfer.files[0]);
          }}
          className={`relative mt-10 grid min-h-56 cursor-pointer place-items-center rounded-media border-2 border-dashed p-8 text-center transition-colors ${
            drag ? "border-transparent" : "border-mist hover:border-slate"
          }`}
        >
          {drag && <span aria-hidden className="voice-ribbon absolute -inset-[2px] -z-10 rounded-media" style={{ ["--to" as string]: lang(langs[0] ?? "ta-IN").hue }} />}
          {drag && <span aria-hidden className="absolute inset-0 -z-10 rounded-[18px] bg-bg" />}
          <div>
            {file ? (
              <>
                <p className="font-display text-xl font-semibold">{file.name}</p>
                <p className="mt-1 text-sm text-slate">{(file.size / 1024 / 1024).toFixed(1)} MB · click to change</p>
              </>
            ) : (
              <>
                <p className="font-display text-xl font-semibold">Drop your video here</p>
                <p className="mt-1 text-sm text-slate">or click to choose · MP4, MOV, WebM · up to 3 minutes</p>
              </>
            )}
          </div>
          <input ref={input} type="file" accept="video/*" className="sr-only" onChange={(e) => pick(e.target.files?.[0])} />
        </div>

        <fieldset className="mt-10">
          <legend className="font-display text-lg font-semibold">Dub into</legend>
          <div className="mt-3 flex flex-wrap gap-2.5">
            {TARGET_LANGS.map((l) => (
              <LanguageChip key={l.code} code={l.code} selected={langs.includes(l.code)} onClick={() => toggle(l.code)} />
            ))}
          </div>
        </fieldset>

        <fieldset className="mt-10">
          <legend className="font-display text-lg font-semibold">Voice</legend>
          <div className="mt-3 grid gap-2.5 sm:grid-cols-2">
            <label className={`flex cursor-pointer items-start gap-3 rounded-panel border p-4 ${voiceId ? "border-mist" : "border-fg"}`}>
              <input type="radio" name="voice" checked={!voiceId} onChange={() => setVoiceId("")} className="mt-1.5" />
              <span>
                <span className="block font-display font-semibold">Stock voice</span>
                <span className="text-sm text-slate">A natural studio voice for each language.</span>
              </span>
            </label>
            <label className={`flex items-start gap-3 rounded-panel border p-4 ${voices.length ? "cursor-pointer" : "opacity-60"} ${voiceId ? "border-fg" : "border-mist"}`}>
              <input type="radio" name="voice" disabled={!voices.length} checked={!!voiceId} onChange={() => setVoiceId(voices[0]?.id ?? "")} className="mt-1.5" />
              <span>
                <span className="block font-display font-semibold">My voice</span>
                {voices.length ? (
                  <select value={voiceId || voices[0].id} onChange={(e) => setVoiceId(e.target.value)} className="mt-1 rounded-panel border border-mist bg-surface px-2 py-1 text-sm" aria-label="Voice profile">
                    {voices.map((v) => <option key={v.id} value={v.id}>{v.display_name}</option>)}
                  </select>
                ) : (
                  <span className="text-sm text-slate">
                    <Link href="/voices" className="underline underline-offset-2">Record your voice</Link> first, with consent.
                  </span>
                )}
              </span>
            </label>
          </div>
        </fieldset>

        <label className="mt-10 flex cursor-pointer items-start gap-3">
          <input type="checkbox" checked={owns} onChange={(e) => setOwns(e.target.checked)} className="mt-1.5 size-4" />
          <span>I own this video or have permission to dub it.</span>
        </label>

        {error && <p role="alert" className="mt-6 rounded-panel border border-[var(--bn)] px-4 py-3 text-sm">{error}</p>}

        <Button size="lg" className="mt-8 w-full sm:w-auto" disabled={!file || !langs.length || !owns || busy} onClick={submit}>
          {busy ? "Uploading…" : "Start dubbing"}
        </Button>

        {jobs.length > 0 && (
          <section className="mt-20" aria-labelledby="recent-h">
            <h2 id="recent-h" className="font-display text-lg font-semibold">Recent videos</h2>
            <ul className="mt-3 divide-y divide-mist border-y border-mist">
              {jobs.slice(0, 8).map((j) => (
                <li key={j.id}>
                  <Link href={`/studio/${j.id}`} className="flex items-center justify-between gap-4 py-3 hover:bg-surface">
                    <span className="truncate">{j.source_path}</span>
                    <span className="flex shrink-0 items-center gap-3 text-sm text-slate">
                      {j.target_langs.map((c) => <span key={c} className="size-2 rounded-full" style={{ background: lang(c).hue }} title={lang(c).name} />)}
                      <span>{j.status}</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}
        <p className="sr-only">API: {API_BASE}</p>
      </main>
    </>
  );
}
