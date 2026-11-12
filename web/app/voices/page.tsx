"use client";
import { useEffect, useRef, useState } from "react";
import { Nav } from "@/components/layout/Nav";
import { Button } from "@/components/ui/Button";
import { useAudioLevel } from "@/components/voice/useAudioLevel";
import { api, type VoiceProfile } from "@/lib/api";

const consentSentence = (name: string) =>
  `I, ${name || "[your name]"}, agree that Bharat Dub may create a copy of my voice to dub my own videos and live streams. I can delete it at any time.`;
const MIN_S = 5;
const MAX_S = 30;

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
  const level = useAudioLevel(src, ctx);
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
    <>
      <Nav />
      <main className="mx-auto max-w-3xl px-4 py-12 sm:px-8 sm:py-16">
        <h1 className="font-display text-[clamp(2rem,5vw,3rem)] font-semibold leading-tight">Your voice</h1>
        <p className="mt-3 max-w-[60ch] text-slate">
          Record 20 to 30 seconds in a quiet room. Read the sentence below aloud first, then keep talking naturally, the way you do on camera.
        </p>

        <label className="mt-10 block max-w-sm">
          <span className="font-display font-semibold">Your name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} className="mt-2 h-12 w-full rounded-panel border border-mist bg-surface px-4" />
        </label>

        <blockquote className="mt-8 border-l-4 border-[var(--hi)] pl-5 font-display text-[clamp(1.3rem,3vw,1.9rem)] leading-snug">
          {consentSentence(name.trim())}
        </blockquote>

        <div className="mt-10 flex flex-wrap items-center gap-6">
          <button
            onClick={() => (recording ? rec?.stop() : start())}
            aria-label={recording ? "Stop recording" : "Start recording"}
            className="relative grid size-24 place-items-center rounded-chip bg-[var(--bn)] text-white"
          >
            <span aria-hidden className="absolute inset-0 rounded-chip bg-[var(--bn)] opacity-30" style={{ transform: `scale(${1 + level * 0.6})` }} />
            <span className="relative font-display font-semibold">{recording ? "Stop" : "Record"}</span>
          </button>
          <div>
            <p className="tnum font-display text-3xl">{secs.toFixed(0)} s</p>
            <p className="text-sm text-slate">{recording ? `Recording… stops at ${MAX_S} s` : blob ? "Recorded. Listen back below." : `At least ${MIN_S} s, best 20-30 s`}</p>
          </div>
          <label className="text-sm">
            <span className="text-slate">or upload a file </span>
            <input type="file" accept="audio/*" onChange={(e) => e.target.files?.[0] && setSample(e.target.files[0], 0)} className="text-sm" />
          </label>
        </div>

        {blobUrl && <audio controls src={blobUrl} className="mt-6 w-full" />}

        <label className="mt-8 flex cursor-pointer items-start gap-3">
          <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} className="mt-1.5 size-4" />
          <span>This is my voice, and I read the consent sentence aloud in the recording.</span>
        </label>
        {msg && <p role="status" className="mt-5 rounded-panel border border-mist px-4 py-3 text-sm">{msg}</p>}
        <Button size="lg" className="mt-6" disabled={!blob || !agree || !name.trim() || busy || (secs > 0 && secs < MIN_S)} onClick={saveVoice}>
          {busy ? "Creating your voice…" : "Save voice"}
        </Button>

        <section className="mt-16" aria-labelledby="saved-h">
          <h2 id="saved-h" className="font-display text-lg font-semibold">Saved voices</h2>
          {voices.length ? (
            <ul className="mt-3 divide-y divide-mist border-y border-mist">
              {voices.map((v) => (
                <li key={v.id} className="flex items-center justify-between gap-4 py-3">
                  <span>
                    <span className="font-display font-semibold">{v.display_name}</span>
                    <span className="block text-sm text-slate">Consent recorded {new Date(v.consent_at).toLocaleString()}</span>
                  </span>
                  <Button variant="secondary" size="sm" onClick={() => remove(v)}>Delete voice</Button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-slate">None yet.</p>
          )}
        </section>
      </main>
    </>
  );
}
