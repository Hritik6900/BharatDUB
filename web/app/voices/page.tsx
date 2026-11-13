"use client";
import { useEffect, useRef, useState } from "react";
import { Check, Mic, Quote, ShieldCheck, Square, Trash2, Upload } from "lucide-react";
import { Shell } from "@/components/layout/Shell";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { VoiceBars } from "@/components/voice/VoiceBars";
import { VoiceOrb } from "@/components/voice/VoiceOrb";
import { api, type VoiceProfile } from "@/lib/api";
import { useAnalyser } from "@/lib/useMic";

const consentSentence = (name: string) =>
  `I, ${name || "[your name]"}, agree that Bharat Dub may create a copy of my voice to dub my own videos and live streams. I can delete it at any time.`;
const MIN_S = 5;
const MAX_S = 30;
const TIPS = ["A quiet room, no music or fan noise", "Phone or headset mic close to your mouth", "Talk the way you do on camera, not like reading"];

export default function VoicesPage() {
  const [voices, setVoices] = useState<VoiceProfile[]>([]);
  const [name, setName] = useState("");
  const [blob, setBlob] = useState<Blob | null>(null);
  const [blobUrl, setBlobUrl] = useState("");
  const [secs, setSecs] = useState(0);
  const [rec, setRec] = useState<MediaRecorder | null>(null);
  const [ctx, setCtx] = useState<AudioContext | null>(null);
  const [src, setSrc] = useState<MediaStreamAudioSourceNode | null>(null);
  const [agree, setAgree] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const timer = useRef<ReturnType<typeof setInterval>>(undefined);
  const upload = useRef<HTMLInputElement>(null);
  const analyser = useAnalyser(src, ctx);
  const load = () => api<VoiceProfile[]>("/api/voices").then(setVoices).catch(() => {});
  useEffect(() => {
    load();
  }, []);

  const setSample = (b: Blob | null, duration = 0) => {
    if (blobUrl) URL.revokeObjectURL(blobUrl);
    setBlob(b);
    setBlobUrl(b ? URL.createObjectURL(b) : "");
    setSecs(duration);
  };

  const start = async () => {
    setMsg("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, noiseSuppression: true } });
      const c = new AudioContext();
      setCtx(c);
      setSrc(c.createMediaStreamSource(stream));
      const r = new MediaRecorder(stream);
      const chunks: Blob[] = [];
      const t0 = Date.now();
      r.ondataavailable = (e) => chunks.push(e.data);
      r.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        void c.close();
        setSrc(null);
        setCtx(null);
        clearInterval(timer.current);
        setSample(new Blob(chunks, { type: r.mimeType }), (Date.now() - t0) / 1000);
        setRec(null);
      };
      r.start();
      setRec(r);
      setSecs(0);
      timer.current = setInterval(() => {
        const s = (Date.now() - t0) / 1000;
        setSecs(s);
        if (s >= MAX_S) r.stop();
      }, 200);
    } catch (e) {
      setMsg(`Microphone: ${(e as Error).message}`);
    }
  };

  const saveVoice = async () => {
    if (!blob) return;
    setBusy(true);
    setMsg("");
    const fd = new FormData();
    const ext = blob.type.includes("webm") ? "webm" : blob.type.includes("ogg") ? "ogg" : blob.type.includes("mp4") ? "m4a" : "wav";
    fd.append("sample", blob, `sample.${ext}`);
    fd.append("consent_text", consentSentence(name.trim()));
    fd.append("consent", String(agree));
    fd.append("display_name", name.trim() || "My voice");
    try {
      await api("/api/voices", { method: "POST", body: fd });
      setMsg("Voice saved.");
      setSample(null);
      setAgree(false);
      load();
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (v: VoiceProfile) => {
    if (!confirm(`Delete "${v.display_name}"? The sample and the voice copy are removed.`)) return;
    await api(`/api/voices/${v.id}`, { method: "DELETE" }).catch((e) => setMsg((e as Error).message));
    load();
  };

  const recording = !!rec;
  return (
    <Shell>
      <div className="mx-auto max-w-6xl px-5 pb-24 pt-12 sm:px-8 sm:pt-16">
        <PageHeader
          icon={Mic}
          eyebrow="Your voice"
          title={<>Record it <em>once</em></>}
          lede="20 to 30 seconds in a quiet room. Read the consent sentence aloud first, then keep talking naturally, the way you do on camera."
        />

        <div className="mt-12 grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
          <div className="card card-lift rise space-y-9 p-5 sm:p-8">
            <label className="block max-w-sm">
              <span className="text-lg font-medium tracking-[-0.01em]">Your name</span>
              <input value={name} onChange={(e) => setName(e.target.value)} className="input mt-3" autoComplete="name" />
            </label>

            <figure className="rounded-panel bg-sunken p-6 sm:p-7">
              <figcaption className="eyebrow flex items-center gap-2">
                <Quote aria-hidden className="size-3.5" />
                Read this aloud first
              </figcaption>
              <blockquote className="mt-4 font-accent text-[clamp(1.6rem,3.4vw,2.25rem)] italic leading-[1.18]">{consentSentence(name.trim())}</blockquote>
            </figure>

            <div className="flex flex-col items-center gap-6 rounded-panel border border-line p-6 sm:flex-row sm:gap-8">
              <button onClick={() => (recording ? rec?.stop() : start())} aria-label={recording ? "Stop recording" : "Start recording"} className="relative grid shrink-0 place-items-center rounded-full">
                <VoiceOrb size={132} analyser={analyser} />
                <span className={`absolute grid size-16 place-items-center rounded-full text-white shadow-card transition-colors ${recording ? "bg-fg text-on-fg" : "bg-danger"}`}>
                  {recording ? <Square aria-hidden className="size-5 fill-current" /> : <Mic aria-hidden className="size-6" />}
                </span>
              </button>
              <div className="min-w-0 flex-1 text-center sm:text-left">
                <p className="tnum h-display text-5xl">
                  {secs.toFixed(0)}
                  <span className="ml-1 text-2xl text-muted">s</span>
                </p>
                <p className="mt-1 text-sm text-muted" role="status">
                  {recording ? `Recording… stops at ${MAX_S} s` : blob ? "Recorded. Listen back below." : `At least ${MIN_S} s, best 20 to 30 s`}
                </p>
                <VoiceBars analyser={analyser} active={false} bars={40} height={36} colors={["--hi", "--bn", "--te"]} className="mt-3" />
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3 text-sm text-muted">
              <span>Already have a recording?</span>
              <Button variant="secondary" size="sm" onClick={() => upload.current?.click()}>
                <Upload aria-hidden className="size-4" />
                Upload a file
              </Button>
              <input ref={upload} type="file" accept="audio/*" className="sr-only" aria-label="Upload a voice sample" onChange={(e) => e.target.files?.[0] && setSample(e.target.files[0], 0)} />
            </div>

            {blobUrl && <audio controls src={blobUrl} className="w-full" />}

            <div>
              <label className="flex cursor-pointer items-start gap-3">
                <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} className="mt-1 size-4" />
                <span>This is my voice, and I read the consent sentence aloud in the recording.</span>
              </label>
              {msg && <div className="mt-5"><Notice>{msg}</Notice></div>}
              <Button size="lg" className="mt-6" disabled={!blob || !agree || !name.trim() || busy || (secs > 0 && secs < MIN_S)} onClick={saveVoice}>
                <ShieldCheck aria-hidden className="size-4" />
                {busy ? "Creating your voice…" : "Save voice"}
              </Button>
            </div>
          </div>

          <aside className="rise space-y-6" style={{ animationDelay: "0.08s" }}>
            <section className="card p-6" aria-labelledby="saved-h">
              <h2 id="saved-h" className="eyebrow">Saved voices</h2>
              {voices.length ? (
                <ul className="mt-3 divide-y divide-line">
                  {voices.map((v) => (
                    <li key={v.id} className="flex items-center gap-3 py-3.5">
                      <span className="grid size-10 shrink-0 place-items-center rounded-full border border-line bg-bg">
                        <Mic aria-hidden className="size-[18px]" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-medium">{v.display_name}</span>
                        <span className="block text-xs text-muted">Consent recorded {new Date(v.consent_at).toLocaleString()}</span>
                      </span>
                      <button onClick={() => remove(v)} aria-label={`Delete ${v.display_name}`} className="grid size-9 shrink-0 place-items-center rounded-full text-muted transition-colors hover:bg-sunken hover:text-danger">
                        <Trash2 aria-hidden className="size-4" />
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-4 text-sm text-muted">None yet. Your saved voice appears here, with a delete button.</p>
              )}
            </section>

            <section className="card p-6" aria-labelledby="tips-h">
              <h2 id="tips-h" className="eyebrow">For a good copy</h2>
              <ul className="mt-4 space-y-3">
                {TIPS.map((t) => (
                  <li key={t} className="flex items-start gap-2.5">
                    <Check aria-hidden className="mt-1 size-4 shrink-0 text-ok" />
                    {t}
                  </li>
                ))}
              </ul>
            </section>

            <section className="card p-6">
              <h2 className="eyebrow flex items-center gap-2">
                <ShieldCheck aria-hidden className="size-3.5" />
                Consent
              </h2>
              <p className="mt-3 text-sm text-muted">Without the consent sentence and the checkbox, no copy of a voice is made. Deleting a voice removes the sample and the copy.</p>
            </section>
          </aside>
        </div>
      </div>
    </Shell>
  );
}
