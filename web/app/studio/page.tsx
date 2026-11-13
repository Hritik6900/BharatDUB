"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, AudioLines, Captions, Check, ChevronRight, Clapperboard, FileVideo, Mic, Music2, PencilLine, Upload } from "lucide-react";
import { Shell } from "@/components/layout/Shell";
import { Button } from "@/components/ui/Button";
import { LanguageChip } from "@/components/ui/LanguageChip";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { api, type Job, type VoiceProfile } from "@/lib/api";
import { TARGET_LANGS, lang } from "@/lib/langs";

const MAX_MB = 500;
// Same sentence the backend stores on the voice profile it creates from the video.
const VIDEO_VOICE_CONSENT =
  "The voice in this video is mine, or I have the speaker's permission, and I agree that Bharat Dub may make a copy of it to dub this video.";
const GET = [
  { icon: FileVideo, text: "A dubbed MP4 for each language" },
  { icon: Captions, text: "A subtitle file for each language" },
  { icon: Music2, text: "Your background music and sound kept" },
  { icon: PencilLine, text: "A line editor to fix any translation" },
];
const STATUS: Record<Job["status"], string> = { queued: "Queued", running: "Dubbing", done: "Ready", failed: "Stopped", expired: "Expired" };

function StepLabel({ n, children }: { n: number; children: React.ReactNode }) {
  return (
    <legend className="flex items-center gap-3 text-lg font-medium tracking-[-0.01em]">
      <span className="tnum grid size-7 place-items-center rounded-full bg-fg font-mono text-xs text-on-fg">{n}</span>
      {children}
    </legend>
  );
}

export default function StudioPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [drag, setDrag] = useState(false);
  const [langs, setLangs] = useState<string[]>(["ta-IN"]);
  const [voices, setVoices] = useState<VoiceProfile[]>([]);
  const [voiceId, setVoiceId] = useState<string>("");
  const [voiceMode, setVoiceMode] = useState<"video" | "stock" | "saved">("video");
  const [voiceConsent, setVoiceConsent] = useState(false);
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
    if (voiceMode === "saved" && voiceId) fd.append("voice_profile_id", voiceId);
    if (voiceMode === "video") {
      fd.append("voice_from_video", "true");
      fd.append("voice_consent", String(voiceConsent));
    }
    try {
      const { job_id } = await api<{ job_id: string }>("/api/jobs", { method: "POST", body: fd });
      router.push(`/studio/${job_id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };

  const radio = (on: boolean, enabled = true) =>
    `flex items-start gap-3.5 rounded-panel border p-4 transition-colors ${enabled ? "cursor-pointer" : "opacity-60"} ${on ? "border-fg bg-surface" : "border-line bg-surface/60 hover:border-fg/40"}`;

  return (
    <Shell>
      <div className="mx-auto max-w-6xl px-5 pb-24 pt-12 sm:px-8 sm:pt-16">
        <PageHeader icon={Clapperboard} eyebrow="Studio" title={<>Dub a <em>video</em></>} lede="A reel, short or clip up to 3 minutes. You get it back dubbed, with subtitles, one video per language." />

        <div className="mt-12 grid gap-8 lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
          <div className="card card-lift rise space-y-10 p-5 sm:p-8">
            <fieldset>
              <StepLabel n={1}>Your video</StepLabel>
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
                className={`relative mt-4 grid min-h-56 cursor-pointer place-items-center rounded-panel p-8 text-center transition-colors ${drag ? "bg-sunken" : "bg-bg hover:bg-sunken"}`}
              >
                <span aria-hidden className={`pointer-events-none absolute inset-0 rounded-panel border-2 border-dashed transition-colors ${drag ? "border-fg" : file ? "border-ok" : "border-line"}`} />
                <div className="flex flex-col items-center">
                  <span className={`grid size-14 place-items-center rounded-full border border-line bg-surface ${file ? "text-ok" : ""}`}>
                    {file ? <Check aria-hidden className="size-6" /> : <Upload aria-hidden className="size-6" />}
                  </span>
                  {file ? (
                    <>
                      <p className="mt-4 max-w-full break-all text-lg font-medium">{file.name}</p>
                      <p className="mt-1 text-sm text-muted">{(file.size / 1024 / 1024).toFixed(1)} MB · click to change</p>
                    </>
                  ) : (
                    <>
                      <p className="mt-4 text-lg font-medium">Drop your video here</p>
                      <p className="mt-1 text-sm text-muted">or click to choose · MP4, MOV, WebM · up to 3 minutes</p>
                    </>
                  )}
                </div>
                <input ref={input} type="file" accept="video/*" className="sr-only" onChange={(e) => pick(e.target.files?.[0])} />
              </div>
            </fieldset>

            <fieldset>
              <StepLabel n={2}>Dub into</StepLabel>
              <div className="mt-4 flex flex-wrap gap-2.5">
                {TARGET_LANGS.map((l) => (
                  <LanguageChip key={l.code} code={l.code} selected={langs.includes(l.code)} onClick={() => toggle(l.code)} />
                ))}
              </div>
            </fieldset>

            <fieldset>
              <StepLabel n={3}>Voice</StepLabel>
              <div className="mt-4 grid gap-3">
                <label className={radio(voiceMode === "video")}>
                  <input type="radio" name="voice" checked={voiceMode === "video"} onChange={() => setVoiceMode("video")} className="mt-1 size-4" />
                  <span>
                    <span className="flex items-center gap-2 font-medium">
                      <FileVideo aria-hidden className="size-4" />
                      Voice in this video
                    </span>
                    <span className="text-sm text-muted">Copied from the speech in the video itself. Nothing to record.</span>
                  </span>
                </label>
                <label className={radio(voiceMode === "stock")}>
                  <input type="radio" name="voice" checked={voiceMode === "stock"} onChange={() => setVoiceMode("stock")} className="mt-1 size-4" />
                  <span>
                    <span className="flex items-center gap-2 font-medium">
                      <AudioLines aria-hidden className="size-4" />
                      Stock voice
                    </span>
                    <span className="text-sm text-muted">A natural studio voice for each language.</span>
                  </span>
                </label>
                <label className={radio(voiceMode === "saved", voices.length > 0)}>
                  <input
                    type="radio"
                    name="voice"
                    disabled={!voices.length}
                    checked={voiceMode === "saved"}
                    onChange={() => {
                      setVoiceMode("saved");
                      setVoiceId((id) => id || voices[0]?.id || "");
                    }}
                    className="mt-1 size-4"
                  />
                  <span className="min-w-0">
                    <span className="flex items-center gap-2 font-medium">
                      <Mic aria-hidden className="size-4" />
                      Saved voice
                    </span>
                    {voices.length ? (
                      <select
                        value={voiceId || voices[0].id}
                        onChange={(e) => {
                          setVoiceId(e.target.value);
                          setVoiceMode("saved");
                        }}
                        className="input mt-2 h-9 px-2 text-sm"
                        aria-label="Voice profile"
                      >
                        {voices.map((v) => <option key={v.id} value={v.id}>{v.display_name}</option>)}
                      </select>
                    ) : (
                      <span className="text-sm text-muted">
                        None yet. <Link href="/voices" className="text-fg underline underline-offset-2">Record one</Link>.
                      </span>
                    )}
                  </span>
                </label>
              </div>
              {voiceMode === "video" && (
                <div className="mt-4 rounded-panel bg-sunken p-4">
                  <label className="flex cursor-pointer items-start gap-3">
                    <input type="checkbox" checked={voiceConsent} onChange={(e) => setVoiceConsent(e.target.checked)} className="mt-1 size-4" />
                    <span>{VIDEO_VOICE_CONSENT}</span>
                  </label>
                  <p className="mt-2 pl-7 text-sm text-muted">
                    Needs at least 5 seconds of clear speech; with less, a stock voice is used. Works best with one speaker. The copy is saved under
                    Your voice, where you can delete it or reuse it for Live.
                  </p>
                </div>
              )}
            </fieldset>

            <div>
              <label className="flex cursor-pointer items-start gap-3">
                <input type="checkbox" checked={owns} onChange={(e) => setOwns(e.target.checked)} className="mt-1 size-4" />
                <span>I own this video or have permission to dub it.</span>
              </label>
              {error && <div className="mt-5"><Notice tone="error" role="alert">{error}</Notice></div>}
              <Button size="lg" className="mt-6 w-full sm:w-auto" disabled={!file || !langs.length || !owns || busy || (voiceMode === "video" && !voiceConsent)} onClick={submit}>
                {busy ? "Uploading…" : "Start dubbing"}
                <ArrowRight aria-hidden className="size-4 transition-transform group-hover:translate-x-0.5" />
              </Button>
            </div>
          </div>

          <aside className="rise space-y-6" style={{ animationDelay: "0.08s" }}>
            <section className="card p-6" aria-labelledby="get-h">
              <h2 id="get-h" className="eyebrow">What you get</h2>
              <ul className="mt-5 space-y-4">
                {GET.map((g) => (
                  <li key={g.text} className="flex items-center gap-3.5">
                    <span className="grid size-10 shrink-0 place-items-center rounded-[12px] border border-line bg-bg">
                      <g.icon aria-hidden className="size-[18px]" />
                    </span>
                    {g.text}
                  </li>
                ))}
              </ul>
            </section>

            <section className="card p-6" aria-labelledby="recent-h">
              <h2 id="recent-h" className="eyebrow">Recent videos</h2>
              {jobs.length ? (
                <ul className="mt-3 divide-y divide-line">
                  {jobs.slice(0, 6).map((j) => (
                    <li key={j.id}>
                      <Link href={`/studio/${j.id}`} className="group flex items-center gap-3 py-3">
                        <span className="min-w-0 flex-1">
                          <span className="block truncate font-medium">{j.source_path}</span>
                          <span className="mt-0.5 flex items-center gap-2 text-sm text-muted">
                            {STATUS[j.status]}
                            <span className="flex gap-1">
                              {j.target_langs.map((c) => <span key={c} className="size-2 rounded-full" style={{ background: lang(c).hue }} title={lang(c).name} />)}
                            </span>
                          </span>
                        </span>
                        <ChevronRight aria-hidden className="size-4 shrink-0 text-muted transition-transform group-hover:translate-x-0.5" />
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-4 text-sm text-muted">Videos you dub appear here.</p>
              )}
            </section>
          </aside>
        </div>
      </div>
    </Shell>
  );
}
