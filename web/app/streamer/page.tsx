"use client";
/** Streamer Mode: profile -> voice recorded once with consent -> go live in your own voice. */
import { useCallback, useEffect, useRef, useState } from "react";
import { Check, CircleAlert, Mic, Play, Radio, Square, Trash2, UserRound } from "lucide-react";
import { Shell } from "@/components/layout/Shell";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { API_BASE, api } from "@/lib/api";
import { TARGET_LANGS, lang } from "@/lib/langs";

const KEY = "bd-streamer";
const LIVE_KEY = "bd-live-session"; // the console at /live reads the session from here
const INPUT_KEY = "bd-live-input"; // ... and the chosen input device from here
const MIN_S = 15;
const MAX_S = 30;

interface Voice {
  id: string;
  consent_at: string;
  gnani_clone: boolean;
  gpu_voice: boolean;
  ref_score: number | null;
  ref_seconds: number | null;
  ref_cleaned: boolean | null;
  ref_build_s: number | null;
}
interface Streamer {
  id: string;
  handle: string;
  display_name: string;
  youtube_channel: string;
  default_langs: string[];
  src_lang: string;
  voice: Voice | null;
}
interface EngineHealth {
  gnani: boolean;
  llm: boolean;
  gpu_engines: { ok: boolean; ms: number | null }[];
  gpu_separate: boolean;
}

const consentSentence = (name: string) => `I, ${name || "your name"}, agree that Bharat Dub may make a copy of my voice to dub my streams.`;

export default function StreamerPage() {
  const [me, setMe] = useState<Streamer | null>(null);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    let id = "";
    try {
      id = localStorage.getItem(KEY) ?? "";
    } catch {
      /* storage blocked */
    }
    if (!id) return setLoaded(true);
    api<Streamer>(`/api/streamers/${id}`)
      .then(setMe)
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);
  const save = (s: Streamer) => {
    setMe(s);
    try {
      localStorage.setItem(KEY, s.id);
    } catch {
      /* storage blocked */
    }
  };
  return (
    <Shell>
      <div className="mx-auto max-w-4xl px-5 pb-24 pt-12 sm:px-8 sm:pt-16">
        <PageHeader
          icon={Radio}
          eyebrow="Streamer"
          title={<>Your stream, in <em>your own voice</em></>}
          lede="Record your voice once. Then go live on YouTube as usual: your viewers hear you in their language, from your first sentence."
        />
        <div className="mt-10 space-y-6">
          {!loaded ? null : !me ? <ProfileForm onDone={save} /> : !me.voice ? <VoiceRecorder me={me} onDone={save} /> : (
            <>
              <VoiceCard me={me} onChange={save} />
              <GoLive me={me} />
            </>
          )}
        </div>
      </div>
    </Shell>
  );
}

function ProfileForm({ onDone }: { onDone: (s: Streamer) => void }) {
  const [handle, setHandle] = useState("");
  const [name, setName] = useState("");
  const [channel, setChannel] = useState("");
  const [langs, setLangs] = useState<string[]>(["ta-IN", "bn-IN"]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const toggle = (c: string) => setLangs((l) => (l.includes(c) ? l.filter((x) => x !== c) : l.length >= 4 ? l : [...l, c]));
  const create = async () => {
    setBusy(true);
    setErr("");
    try {
      onDone(await api<Streamer>("/api/streamers", { method: "POST", body: JSON.stringify({ handle, display_name: name, youtube_channel: channel, default_langs: langs }) }));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="card space-y-6 p-5 sm:p-8" aria-labelledby="p-h">
      <h2 id="p-h" className="eyebrow flex items-center gap-2"><UserRound aria-hidden className="size-3.5" />Step 1 of 3: your profile</h2>
      <label className="block">
        <span className="font-medium">Handle</span>
        <input value={handle} onChange={(e) => setHandle(e.target.value.toLowerCase())} placeholder="your_handle" maxLength={24} className="input mt-2" />
        <span className="mt-1 block text-sm text-muted">3 to 24 letters, digits or underscores.</span>
      </label>
      <label className="block">
        <span className="font-medium">Name viewers see</span>
        <input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} className="input mt-2" />
      </label>
      <label className="block">
        <span className="font-medium">YouTube channel (optional)</span>
        <input value={channel} onChange={(e) => setChannel(e.target.value)} placeholder="https://youtube.com/@…" className="input mt-2" />
      </label>
      <LangPicker langs={langs} toggle={toggle} label="Languages you want to be heard in (up to 4)" />
      {err && <Notice tone="error" role="alert">{err}</Notice>}
      <Button size="lg" onClick={create} disabled={busy || !handle || !name.trim() || !langs.length}>{busy ? "Saving…" : "Continue"}</Button>
    </section>
  );
}

function LangPicker({ langs, toggle, label, only }: { langs: string[]; toggle: (c: string) => void; label: string; only?: string[] }) {
  return (
    <fieldset>
      <legend className="font-medium">{label}</legend>
      <div className="mt-3 flex flex-wrap gap-2">
        {(only ?? TARGET_LANGS.map((l) => l.code)).map((c) => {
          const on = langs.includes(c);
          return (
            <button key={c} type="button" role="checkbox" aria-checked={on} onClick={() => toggle(c)}
              className={`inline-flex h-10 items-center gap-2 rounded-chip border px-4 text-sm transition-colors ${on ? "border-fg bg-fg text-on-fg" : "border-line bg-surface hover:border-fg/50"}`}>
              <span aria-hidden className="size-2 rounded-full" style={{ background: lang(c).hue }} />
              {lang(c).name}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

function VoiceRecorder({ me, onDone }: { me: Streamer; onDone: (s: Streamer) => void }) {
  const [rec, setRec] = useState<MediaRecorder | null>(null);
  const [secs, setSecs] = useState(0);
  const [blob, setBlob] = useState<Blob | null>(null);
  const [agree, setAgree] = useState(false);
  const [busy, setBusy] = useState(false);
  const [waited, setWaited] = useState(0);
  const [err, setErr] = useState("");
  const timer = useRef<ReturnType<typeof setInterval>>(undefined);
  useEffect(() => () => clearInterval(timer.current), []);

  const start = async () => {
    setErr("");
    setBlob(null);
    try {
      // Untouched sound: the browser's noise and echo filters change a voice, and the copy would copy that.
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: false } });
      const r = new MediaRecorder(stream);
      const chunks: Blob[] = [];
      const t0 = Date.now();
      r.ondataavailable = (e) => chunks.push(e.data);
      r.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        clearInterval(timer.current);
        setBlob(new Blob(chunks, { type: r.mimeType }));
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
      setErr(`Microphone: ${(e as Error).message}`);
    }
  };
  const upload = async () => {
    if (!blob) return;
    setBusy(true);
    setErr("");
    const t0 = Date.now();
    const tick = setInterval(() => setWaited((Date.now() - t0) / 1000), 500);
    const fd = new FormData();
    const ext = blob.type.includes("webm") ? "webm" : blob.type.includes("ogg") ? "ogg" : blob.type.includes("mp4") ? "m4a" : "wav";
    fd.append("sample", blob, `voice.${ext}`);
    fd.append("consent_text", consentSentence(me.display_name));
    fd.append("consent", String(agree));
    try {
      onDone(await api<Streamer>(`/api/streamers/${me.id}/voice`, { method: "POST", body: fd }));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      clearInterval(tick);
      setBusy(false);
    }
  };
  return (
    <section className="card space-y-6 p-5 sm:p-8" aria-labelledby="v-h">
      <h2 id="v-h" className="eyebrow flex items-center gap-2"><Mic aria-hidden className="size-3.5" />Step 2 of 3: your voice</h2>
      <p className="text-muted">Quiet room, 20 to 30 seconds. Read this sentence aloud first, then keep talking the way you do on stream.</p>
      <blockquote className="font-accent text-[clamp(1.4rem,3vw,1.9rem)] italic leading-snug">{consentSentence(me.display_name)}</blockquote>
      <div className="flex flex-wrap items-center gap-4">
        {rec ? (
          <Button variant="danger" size="lg" onClick={() => rec.stop()} disabled={secs < MIN_S}>
            <Square aria-hidden className="size-4 fill-current" />
            {secs < MIN_S ? `Keep talking (${Math.ceil(MIN_S - secs)} s)` : "Stop"}
          </Button>
        ) : (
          <Button size="lg" onClick={start} disabled={busy}><Mic aria-hidden className="size-5" />{blob ? "Record again" : "Record"}</Button>
        )}
        <span className="tnum font-mono text-sm text-muted" aria-live="polite">{rec ? `${secs.toFixed(0)} s of ${MAX_S}` : blob ? `${secs.toFixed(0)} s recorded` : ""}</span>
      </div>
      {blob && !rec && (
        <>
          <label className="flex items-start gap-3">
            <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} className="mt-1 size-5" />
            <span>This is my voice, and I read the consent sentence aloud in the recording.</span>
          </label>
          <Button size="lg" onClick={upload} disabled={!agree || busy}>{busy ? `Making your voice… ${waited.toFixed(0)} s` : "Make my voice"}</Button>
          {busy && <p className="text-sm text-muted">This takes about 20 seconds: the recording is cleaned, the best part is picked, and the copy is tested.</p>}
        </>
      )}
      {err && <Notice tone="error" role="alert">{err}</Notice>}
      <p className="text-sm text-muted">Without the sentence and the checkbox, no copy of a voice is made. You can delete it at any time.</p>
    </section>
  );
}

function VoiceCard({ me, onChange }: { me: Streamer; onChange: (s: Streamer) => void }) {
  const v = me.voice!;
  const [playing, setPlaying] = useState("");
  const [timing, setTiming] = useState<Record<string, string>>({});
  const [err, setErr] = useState("");
  const preview = async (code: string) => {
    setErr("");
    setPlaying(code);
    try {
      const t0 = performance.now();
      const r = await fetch(`${API_BASE}/api/streamers/${me.id}/voice/preview?lang=${code}`, { method: "POST" });
      if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: r.statusText }))).detail);
      const url = URL.createObjectURL(await r.blob());
      setTiming((t) => ({ ...t, [code]: `${((performance.now() - t0) / 1000).toFixed(1)} s` }));
      const a = new Audio(url);
      a.onended = () => URL.revokeObjectURL(url);
      await a.play();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setPlaying("");
    }
  };
  const remove = async () => {
    await api(`/api/streamers/${me.id}/voice`, { method: "DELETE" }).catch((e) => setErr((e as Error).message));
    onChange({ ...me, voice: null });
  };
  const score = v.ref_score;
  return (
    <section className="card space-y-5 p-5 sm:p-8" aria-labelledby="vc-h">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="vc-h" className="eyebrow flex items-center gap-2"><Check aria-hidden className="size-3.5" />@{me.handle}: your voice is ready</h2>
        <button onClick={remove} className="inline-flex items-center gap-2 text-sm text-muted hover:text-fg"><Trash2 aria-hidden className="size-4" />Delete my voice</button>
      </div>
      <dl className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
        <div><dt className="text-muted">Test sentence understood</dt><dd className="tnum mt-1 text-xl font-semibold">{score == null ? "not tested" : `${Math.round(score * 100)}%`}</dd></div>
        <div><dt className="text-muted">Sample used</dt><dd className="tnum mt-1 text-xl font-semibold">{v.ref_seconds != null ? `${v.ref_seconds} s` : "none"}</dd></div>
        <div><dt className="text-muted">Made in</dt><dd className="tnum mt-1 text-xl font-semibold">{v.ref_build_s != null ? `${v.ref_build_s} s` : "n/a"}</dd></div>
        <div><dt className="text-muted">Consent recorded</dt><dd className="mt-1">{new Date(v.consent_at).toLocaleString()}</dd></div>
      </dl>
      {!v.gpu_voice && <Notice tone="warn">The fast voice engine was not reachable, so only the slower copy was made. Live, the first language uses it and the others use stock voices.</Notice>}
      {score != null && score < 0.7 && <Notice tone="warn">This recording did not make a clear voice. A quieter room and steady talking usually fix it: delete and record again.</Notice>}
      <div>
        <p className="font-medium">Hear yourself</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {me.default_langs.filter((c) => c !== "en-IN").map((c) => (
            <button key={c} onClick={() => preview(c)} disabled={!!playing} className="inline-flex h-10 items-center gap-2 rounded-chip border border-line bg-surface px-4 text-sm hover:border-fg disabled:opacity-50">
              <Play aria-hidden className="size-4" />
              {playing === c ? "Making…" : lang(c).name}
              {timing[c] && <span className="tnum font-mono text-xs text-muted">{timing[c]}</span>}
            </button>
          ))}
        </div>
      </div>
      {err && <Notice tone="error" role="alert">{err}</Notice>}
    </section>
  );
}

function GoLive({ me }: { me: Streamer }) {
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [device, setDevice] = useState("");
  const [level, setLevel] = useState(0);
  const [yt, setYt] = useState("");
  const [langs, setLangs] = useState<string[]>(me.default_langs);
  const [mode, setMode] = useState<"clone" | "stock">("clone");
  const [health, setHealth] = useState<EngineHealth | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const toggle = (c: string) => setLangs((l) => (l.includes(c) ? l.filter((x) => x !== c) : l.length >= 4 ? l : [...l, c]));

  const listDevices = useCallback(async () => {
    try {
      // Labels appear only after microphone permission has been given once.
      const s = await navigator.mediaDevices.getUserMedia({ audio: true });
      s.getTracks().forEach((t) => t.stop());
      const all = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "audioinput");
      setDevices(all);
      setDevice((d) => d || all[0]?.deviceId || "");
    } catch (e) {
      setErr(`Microphone: ${(e as Error).message}`);
    }
  }, []);
  useEffect(() => {
    void listDevices();
    api<EngineHealth>("/api/streamers/health").then(setHealth).catch(() => {});
  }, [listDevices]);

  // Level meter of the chosen input, exactly as it will be sent (no filters).
  useEffect(() => {
    if (!device) return;
    let stop = false;
    let stream: MediaStream | null = null;
    let ctx: AudioContext | null = null;
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: { deviceId: { exact: device }, echoCancellation: false, noiseSuppression: false, autoGainControl: false } });
        ctx = new AudioContext();
        const an = ctx.createAnalyser();
        an.fftSize = 1024;
        ctx.createMediaStreamSource(stream).connect(an);
        const buf = new Float32Array(an.fftSize);
        const loop = () => {
          if (stop) return;
          an.getFloatTimeDomainData(buf);
          let sum = 0;
          for (const x of buf) sum += x * x;
          setLevel(Math.min(1, Math.sqrt(sum / buf.length) * 6));
          requestAnimationFrame(loop);
        };
        loop();
      } catch {
        setLevel(0);
      }
    })();
    return () => {
      stop = true;
      stream?.getTracks().forEach((t) => t.stop());
      void ctx?.close();
    };
  }, [device]);

  const go = async () => {
    setBusy(true);
    setErr("");
    try {
      const r = await api<{ session_id: string; ingest_token: string }>("/api/live/sessions", {
        method: "POST",
        // 8 s: a usual YouTube "Low latency" delay. The console has a slider to match it to the real stream.
        body: JSON.stringify({ youtube_video_id: yt, target_langs: langs, src_lang: me.src_lang, streamer_id: me.id, voice_mode: mode, offset_ms: 8000 }),
      });
      localStorage.setItem(LIVE_KEY, JSON.stringify({ sid: r.session_id, token: r.ingest_token }));
      localStorage.setItem(INPUT_KEY, device);
      window.location.href = "/live";
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  };
  const enginesUp = health?.gpu_engines.filter((e) => e.ok).length ?? 0;
  return (
    <section className="card space-y-7 p-5 sm:p-8" aria-labelledby="g-h">
      <h2 id="g-h" className="eyebrow flex items-center gap-2"><Radio aria-hidden className="size-3.5" />Step 3 of 3: go live</h2>
      <label className="block">
        <span className="font-medium">Where your voice comes from</span>
        <select value={device} onChange={(e) => setDevice(e.target.value)} className="input mt-2">
          {devices.map((d) => <option key={d.deviceId} value={d.deviceId}>{d.label || "Audio input"}</option>)}
        </select>
        <span className="mt-3 block h-2 overflow-hidden rounded-full bg-sunken" role="meter" aria-label="Input level" aria-valuenow={Math.round(level * 100)} aria-valuemin={0} aria-valuemax={100}>
          <span className="block h-full rounded-full bg-fg transition-[width] duration-75" style={{ width: `${level * 100}%` }} />
        </span>
        <span className="mt-2 block text-sm text-muted">Speak: the bar should move. For a demo with a recording, pick a virtual cable (for example CABLE Output) that carries your player or OBS monitor sound. Wear headphones.</span>
      </label>
      <label className="block">
        <span className="font-medium">Your YouTube live link</span>
        <input value={yt} onChange={(e) => setYt(e.target.value)} placeholder="https://youtube.com/live/…" className="input mt-2" />
        <span className="mt-1 block text-sm text-muted">In YouTube Studio set Stream latency to Low latency. Without a link, viewers get the dub and captions only.</span>
      </label>
      <LangPicker langs={langs} toggle={toggle} label="Languages for this stream" />
      <fieldset>
        <legend className="font-medium">Voice</legend>
        <div className="mt-3 flex flex-wrap gap-2">
          {(["clone", "stock"] as const).map((m) => (
            <button key={m} type="button" role="radio" aria-checked={mode === m} onClick={() => setMode(m)}
              className={`h-10 rounded-chip border px-4 text-sm ${mode === m ? "border-fg bg-fg text-on-fg" : "border-line bg-surface hover:border-fg/50"}`}>
              {m === "clone" ? "My own voice" : "Stock voices"}
            </button>
          ))}
        </div>
        {mode === "clone" && langs.includes("en-IN") && <p className="mt-2 text-sm text-muted">English uses the slower copy of your voice or a stock voice; the other languages use the fast engine.</p>}
      </fieldset>
      {health && (
        <ul className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4" aria-label="Services">
          {[
            ["Speech to text", health.gnani],
            ["Translation", health.llm],
            [`Voice engines ${enginesUp}/${health.gpu_engines.length}`, enginesUp > 0],
            ["Stock voices", health.gnani],
          ].map(([label, ok]) => (
            <li key={String(label)} className="flex items-center gap-2 rounded-panel border border-line px-3 py-2">
              {ok ? <Check aria-hidden className="size-4 text-ok" /> : <CircleAlert aria-hidden className="size-4 text-danger" />}
              {label}
            </li>
          ))}
        </ul>
      )}
      {health && mode === "clone" && enginesUp === 0 && <Notice tone="warn">The fast voice engines are not reachable. You can still go live: your first language uses the slower copy of your voice, the others stock voices.</Notice>}
      {err && <Notice tone="error" role="alert">{err}</Notice>}
      <Button variant="danger" size="lg" onClick={go} disabled={busy || !langs.length || !device}><Radio aria-hidden className="size-5" />{busy ? "Starting…" : "Open my live console"}</Button>
    </section>
  );
}
