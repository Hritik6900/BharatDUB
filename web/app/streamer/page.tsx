"use client";
/** Streamer Mode: profile -> voice recorded once with consent -> go live in your own voice. */
import { useCallback, useEffect, useRef, useState } from "react";
import { AudioLines, Check, CircleAlert, Cpu, Ear, Headphones, Languages, Mic, Play, Radio, RefreshCw, Square, Trash2, UserRound, MonitorPlay, type LucideIcon } from "lucide-react";
import { Shell } from "@/components/layout/Shell";
import { Button } from "@/components/ui/Button";
import { LanguageChip } from "@/components/ui/LanguageChip";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { VoiceBars } from "@/components/voice/VoiceBars";
import { VoiceOrb } from "@/components/voice/VoiceOrb";
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
type SetAnalyser = (a: AnalyserNode | null) => void;

const consentSentence = (name: string) => `I, ${name || "your name"}, agree that Bharat Dub may make a copy of my voice to dub my streams.`;

export default function StreamerPage() {
  const [me, setMe] = useState<Streamer | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [micAn, setMicAn] = useState<AnalyserNode | null>(null); // the input being recorded or tested
  const [playAn, setPlayAn] = useState<AnalyserNode | null>(null); // a preview of the copied voice, while it plays
  const [health, setHealth] = useState<EngineHealth | null | "down">(null);
  const [checkedAt, setCheckedAt] = useState(0);

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
  const check = useCallback(() => {
    api<EngineHealth>("/api/streamers/health")
      .then(setHealth)
      .catch(() => setHealth("down"))
      .finally(() => setCheckedAt(Date.now()));
  }, []);
  useEffect(() => {
    check();
    const id = setInterval(check, 30000);
    return () => clearInterval(id);
  }, [check]);

  const save = (s: Streamer) => {
    setMe(s);
    try {
      localStorage.setItem(KEY, s.id);
    } catch {
      /* storage blocked */
    }
  };
  const step = !me ? 0 : !me.voice ? 1 : 2;
  return (
    <Shell dark>
      <div className="mx-auto max-w-6xl px-5 pb-24 pt-12 sm:px-8 sm:pt-16">
        <PageHeader
          icon={Radio}
          eyebrow="Streamer"
          title={<>Your stream, in <em>your own voice</em></>}
          lede="Record your voice once. Then go live on YouTube as usual: your viewers hear you in their language, from your first sentence."
        />
        <Stepper step={step} me={me} />
        <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
          <div className="min-w-0 space-y-6">
            {!loaded ? (
              <div className="card h-64 animate-pulse" aria-hidden />
            ) : !me ? (
              <ProfileForm onDone={save} />
            ) : !me.voice ? (
              <VoiceRecorder me={me} onDone={save} onAnalyser={setMicAn} />
            ) : (
              <>
                <VoiceCard me={me} onChange={save} onAnalyser={setPlayAn} />
                <GoLive me={me} onAnalyser={setMicAn} health={health === "down" ? null : health} />
              </>
            )}
          </div>
          <aside className="min-w-0 lg:sticky lg:top-28 lg:self-start">
            <SignalPath analyser={playAn ?? micAn} playing={Boolean(playAn)} health={health} checkedAt={checkedAt} onCheck={check} hasVoice={Boolean(me?.voice?.gpu_voice)} />
          </aside>
        </div>
      </div>
    </Shell>
  );
}

const STEPS: { icon: LucideIcon; label: string; sub: string }[] = [
  { icon: UserRound, label: "Profile", sub: "Who you are, which languages" },
  { icon: Mic, label: "Your voice", sub: "20 to 30 seconds, with your consent" },
  { icon: Radio, label: "Go live", sub: "Pick your mic and your stream" },
];

function Stepper({ step, me }: { step: number; me: Streamer | null }) {
  return (
    <ol className="rise mt-10 grid grid-cols-3 gap-2" style={{ animationDelay: "0.06s" }}>
      {STEPS.map((s, i) => {
        const done = i < step;
        const now = i === step;
        return (
          <li key={s.label} aria-current={now ? "step" : undefined} className={`relative overflow-hidden rounded-panel border p-3 transition-colors sm:p-4 ${now ? "border-fg/60 bg-surface" : "border-line bg-surface/50"}`}>
            <span aria-hidden className="absolute inset-x-0 top-0 h-0.5 origin-left transition-transform duration-700" style={{ background: "var(--spectrum)", transform: `scaleX(${done || now ? 1 : 0})`, opacity: done ? 0.55 : 1 }} />
            <span className="flex flex-col items-start gap-2 sm:flex-row sm:items-center sm:gap-3">
              <span className={`grid size-9 shrink-0 place-items-center rounded-full border sm:size-10 ${done ? "border-ok text-ok" : now ? "border-fg bg-fg text-on-fg" : "border-line text-muted"}`}>
                {done ? <Check aria-hidden className="size-4" /> : <s.icon aria-hidden className="size-4" />}
              </span>
              <span className="min-w-0">
                <span className="tnum block font-mono text-[10px] uppercase tracking-[0.14em] text-muted">Step 0{i + 1}</span>
                <span className={`block text-sm font-medium sm:text-base ${now || done ? "" : "text-muted"}`}>{s.label}</span>
              </span>
            </span>
            <span className="mt-2 hidden truncate text-sm text-muted sm:block">{done && i === 0 && me ? `@${me.handle}` : done && i === 1 ? "Recorded and tested" : s.sub}</span>
          </li>
        );
      })}
    </ol>
  );
}

/** The chain a spoken phrase goes through, with what this page can really see of each link. */
function SignalPath({ analyser, playing, health, checkedAt, onCheck, hasVoice }: { analyser: AnalyserNode | null; playing: boolean; health: EngineHealth | null | "down"; checkedAt: number; onCheck: () => void; hasVoice: boolean }) {
  const [, tick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => tick((x) => x + 1), 5000);
    return () => clearInterval(id);
  }, []);
  const h = health && health !== "down" ? health : null;
  const up = h?.gpu_engines.filter((e) => e.ok).length ?? 0;
  const ago = checkedAt ? Math.max(0, Math.round((Date.now() - checkedAt) / 1000)) : null;
  const rows: { icon: LucideIcon; label: string; ok: boolean | null; note: React.ReactNode }[] = [
    { icon: Mic, label: "Your input", ok: analyser && !playing ? true : null, note: analyser && !playing ? "Open, shown above" : "Not open yet" },
    { icon: Ear, label: "Speech to text", ok: h ? h.gnani : null, note: h ? (h.gnani ? "Key set" : "No key") : "Unknown" },
    { icon: Languages, label: "Translation", ok: h ? h.llm : null, note: h ? (h.llm ? "Model set" : "No model") : "Unknown" },
    {
      icon: Cpu,
      label: "Your voice, on our GPU",
      ok: h ? up > 0 : null,
      note: h ? (
        h.gpu_engines.length ? (
          <span className="flex flex-wrap gap-1">
            {h.gpu_engines.map((e, i) => (
              <span key={i} className="tnum inline-flex items-center gap-1 rounded-chip border border-line px-2 py-0.5 font-mono text-[11px]">
                <span className="size-1.5 rounded-full" style={{ background: e.ok ? "var(--ok)" : "var(--danger)" }} />
                {e.ok ? `${e.ms} ms` : "down"}
              </span>
            ))}
          </span>
        ) : (
          "Not set up"
        )
      ) : (
        "Unknown"
      ),
    },
    { icon: AudioLines, label: "Stock voices, as fallback", ok: h ? h.gnani : null, note: h ? (h.gnani ? "Key set" : "No key") : "Unknown" },
    { icon: Headphones, label: "Your viewers", ok: null, note: "Open your link, pick a language" },
  ];
  return (
    <section className="stage rise overflow-hidden rounded-card border border-line p-6" style={{ ["--glow" as string]: playing ? "var(--bn)" : "var(--te)", animationDelay: "0.12s" }} aria-labelledby="sp-h">
      <div className="flex items-center justify-between gap-3">
        <h2 id="sp-h" className="eyebrow flex items-center gap-2">
          <span className={`size-2 rounded-full ${analyser ? "pulse-dot bg-danger" : "bg-muted"}`} />
          Signal path
        </h2>
        <button type="button" onClick={onCheck} className="inline-flex items-center gap-1.5 text-xs text-muted hover:text-fg">
          <RefreshCw aria-hidden className="size-3.5" />
          {ago == null ? "Checking" : `Checked ${ago < 5 ? "just now" : `${ago} s ago`}`}
        </button>
      </div>

      <div className="mt-6 flex flex-col items-center">
        <div className="relative grid size-40 place-items-center">
          {analyser && <span className="ripple" />}
          {analyser && <span className="ripple" style={{ animationDelay: "1.5s" }} />}
          <VoiceOrb size={132} analyser={analyser} />
        </div>
        <div className="mt-2 w-full">
          <VoiceBars analyser={analyser} active={false} bars={40} height={44} colors={playing ? ["--bn", "--te"] : ["--hi", "--bn", "--te"]} />
        </div>
        <p className="mt-2 text-center text-sm text-muted" aria-live="polite">
          {playing ? "Your copied voice, playing now" : analyser ? "Your input, live: speak and it moves" : hasVoice ? "Pick an input to see it here" : "Your mic shows here when you record"}
        </p>
      </div>

      {health === "down" && <div className="mt-5"><Notice tone="error" role="alert">The backend did not answer, so the services below are unknown.</Notice></div>}
      <ol className="relative mt-6 space-y-1">
        <span aria-hidden className="absolute bottom-5 left-[19px] top-5 w-px bg-line" />
        {rows.map((r) => (
          <li key={r.label} className="relative flex items-center gap-3 py-1.5">
            <span className={`grid size-10 shrink-0 place-items-center rounded-full border bg-bg ${r.ok ? "border-ok/60" : r.ok === false ? "border-danger/70" : "border-line"}`}>
              <r.icon aria-hidden className="size-[18px]" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-medium">{r.label}</span>
              <span className="block text-xs text-muted">{r.note}</span>
            </span>
            {r.ok === true && <Check aria-label="ready" className="size-4 shrink-0 text-ok" />}
            {r.ok === false && <CircleAlert aria-label="not ready" className="size-4 shrink-0 text-danger" />}
          </li>
        ))}
      </ol>
      <p className="mt-4 text-xs text-muted">Engine times are measured by this page&apos;s check. For speech and translation it can only see that a key is set, not that the service answers.</p>
    </section>
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
    <section className="card card-lift rise space-y-7 p-5 sm:p-8" aria-labelledby="p-h">
      <h2 id="p-h" className="h-display text-[1.9rem] leading-tight sm:text-[2.3rem]">First, <em>who is streaming?</em></h2>
      <div className="grid gap-6 sm:grid-cols-2">
        <label className="block">
          <span className="font-medium">Handle</span>
          <span className="relative mt-2 block">
            <span aria-hidden className="pointer-events-none absolute inset-y-0 left-4 flex items-center text-muted">@</span>
            <input value={handle} onChange={(e) => setHandle(e.target.value.toLowerCase())} placeholder="your_handle" maxLength={24} className="input" style={{ paddingLeft: "2.25rem" }} />
          </span>
          <span className="mt-1.5 block text-sm text-muted">3 to 24 letters, digits or underscores.</span>
        </label>
        <label className="block">
          <span className="font-medium">Name viewers see</span>
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} className="input mt-2" />
          <span className="mt-1.5 block text-sm text-muted">Also goes into your consent sentence.</span>
        </label>
      </div>
      <label className="block">
        <span className="font-medium">YouTube channel <span className="text-sm font-normal text-muted">optional</span></span>
        <input value={channel} onChange={(e) => setChannel(e.target.value)} placeholder="https://youtube.com/@…" className="input mt-2" />
      </label>
      <LangPicker langs={langs} toggle={toggle} label="Languages you want to be heard in" />
      {err && <Notice tone="error" role="alert">{err}</Notice>}
      <Button size="lg" onClick={create} disabled={busy || !handle || !name.trim() || !langs.length}>{busy ? "Saving…" : "Continue to your voice"}</Button>
    </section>
  );
}

function LangPicker({ langs, toggle, label }: { langs: string[]; toggle: (c: string) => void; label: string }) {
  return (
    <fieldset>
      <legend className="font-medium">{label} <span className="text-sm font-normal text-muted">up to 4</span></legend>
      <div className="mt-3 flex flex-wrap gap-2.5">
        {TARGET_LANGS.map((l) => <LanguageChip key={l.code} code={l.code} selected={langs.includes(l.code)} onClick={() => toggle(l.code)} />)}
      </div>
    </fieldset>
  );
}

/** A ring that fills with `value` (0..1) around its children. */
function Ring({ value, size, hue = "var(--fg)", children }: { value: number; size: number; hue?: string; children: React.ReactNode }) {
  const r = 47;
  const c = 2 * Math.PI * r;
  return (
    <div className="relative grid shrink-0 place-items-center" style={{ width: size, height: size }}>
      <svg aria-hidden viewBox="0 0 100 100" className="absolute inset-0 -rotate-90">
        <circle cx="50" cy="50" r={r} fill="none" stroke="var(--line)" strokeWidth="2" />
        <circle cx="50" cy="50" r={r} fill="none" stroke={hue} strokeWidth="2.5" strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - Math.min(1, Math.max(0, value)))} className="transition-[stroke-dashoffset] duration-300" />
      </svg>
      {children}
    </div>
  );
}

function VoiceRecorder({ me, onDone, onAnalyser }: { me: Streamer; onDone: (s: Streamer) => void; onAnalyser: SetAnalyser }) {
  const [rec, setRec] = useState<MediaRecorder | null>(null);
  const [an, setAn] = useState<AnalyserNode | null>(null);
  const [secs, setSecs] = useState(0);
  const [blob, setBlob] = useState<Blob | null>(null);
  const [agree, setAgree] = useState(false);
  const [busy, setBusy] = useState(false);
  const [waited, setWaited] = useState(0);
  const [err, setErr] = useState("");
  const timer = useRef<ReturnType<typeof setInterval>>(undefined);
  const audio = useRef<AudioContext | null>(null);
  useEffect(
    () => () => {
      clearInterval(timer.current);
      void audio.current?.close();
      onAnalyser(null);
    },
    [onAnalyser],
  );

  const start = async () => {
    setErr("");
    setBlob(null);
    try {
      // Untouched sound: the browser's noise and echo filters change a voice, and the copy would copy that.
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: false } });
      const ctx = new AudioContext();
      const node = ctx.createAnalyser();
      node.fftSize = 1024;
      node.smoothingTimeConstant = 0.8;
      ctx.createMediaStreamSource(stream).connect(node);
      audio.current = ctx;
      setAn(node);
      onAnalyser(node);
      const r = new MediaRecorder(stream);
      const chunks: Blob[] = [];
      const t0 = Date.now();
      r.ondataavailable = (e) => chunks.push(e.data);
      r.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        clearInterval(timer.current);
        void ctx.close();
        audio.current = null;
        setAn(null);
        onAnalyser(null);
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
  const enough = secs >= MIN_S;
  return (
    <section className="card card-lift rise space-y-7 p-5 sm:p-8" aria-labelledby="v-h">
      <h2 id="v-h" className="h-display text-[1.9rem] leading-tight sm:text-[2.3rem]">Now, <em>your voice</em></h2>
      <div className="tex-tint rounded-panel border border-line p-5 sm:p-6">
        <p className="eyebrow">Read this aloud first</p>
        <blockquote className="mt-3 font-accent text-[clamp(1.4rem,3vw,1.9rem)] italic leading-snug">{consentSentence(me.display_name)}</blockquote>
        <p className="mt-3 text-sm text-muted">Then keep talking the way you do on stream, in Hindi or Hinglish. Quiet room, 20 to 30 seconds.</p>
      </div>

      <div className="flex flex-col items-center gap-6 sm:flex-row">
        <Ring value={rec || blob ? secs / MAX_S : 0} size={168} hue={enough ? "var(--ok)" : "var(--hi)"}>
          <VoiceOrb size={118} analyser={an} />
        </Ring>
        <div className="min-w-0 flex-1 text-center sm:text-left">
          <p className="tnum font-mono text-4xl font-medium tracking-tight" aria-live="polite">
            {secs.toFixed(0)}
            <span className="text-lg text-muted"> / {MAX_S} s</span>
          </p>
          <p className="mt-1 text-sm text-muted">
            {rec ? (enough ? "Long enough. Stop when you like, or go on to 30." : `Keep talking: ${Math.ceil(MIN_S - secs)} s more needed.`) : blob ? "Recorded. Tick the box to make your voice, or record again." : "The ring turns green once the recording is long enough."}
          </p>
          <div className="mt-3">
            <VoiceBars analyser={an} active={false} bars={36} height={40} colors={["--hi", "--bn"]} />
          </div>
          <div className="mt-4 flex flex-wrap justify-center gap-3 sm:justify-start">
            {rec ? (
              <Button variant="danger" size="lg" onClick={() => rec.stop()} disabled={!enough}>
                <Square aria-hidden className="size-4 fill-current" />
                Stop
              </Button>
            ) : (
              <Button size="lg" variant={blob ? "secondary" : "primary"} onClick={start} disabled={busy}>
                <Mic aria-hidden className="size-5" />
                {blob ? "Record again" : "Record"}
              </Button>
            )}
          </div>
        </div>
      </div>

      {blob && !rec && (
        <div className="space-y-5 border-t border-line pt-6">
          <label className="flex items-start gap-3">
            <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} className="mt-1 size-5" />
            <span>This is my voice, and I read the consent sentence aloud in the recording.</span>
          </label>
          <Button size="lg" onClick={upload} disabled={!agree || busy}>{busy ? `Making your voice… ${waited.toFixed(0)} s` : "Make my voice"}</Button>
          {busy && (
            <ul className="grid gap-2 text-sm sm:grid-cols-3">
              {["The recording is cleaned", "The clearest 7 seconds are picked", "A test sentence is spoken and heard back"].map((t) => (
                <li key={t} className="flex items-start gap-2 rounded-panel border border-line bg-sunken px-3 py-2.5">
                  <span aria-hidden className="pulse-dot mt-1.5 size-1.5 shrink-0 rounded-full bg-fg" />
                  {t}
                </li>
              ))}
            </ul>
          )}
          {busy && <p className="text-sm text-muted">One request does all three, usually in about 20 seconds.</p>}
        </div>
      )}
      {err && <Notice tone="error" role="alert">{err}</Notice>}
      <p className="text-sm text-muted">Without the sentence and the checkbox, no copy of a voice is made. You can delete it at any time.</p>
    </section>
  );
}

function VoiceCard({ me, onChange, onAnalyser }: { me: Streamer; onChange: (s: Streamer) => void; onAnalyser: SetAnalyser }) {
  const v = me.voice!;
  const [playing, setPlaying] = useState("");
  const [timing, setTiming] = useState<Record<string, string>>({});
  const [err, setErr] = useState("");
  const audio = useRef<AudioContext | null>(null);
  useEffect(
    () => () => {
      void audio.current?.close();
      onAnalyser(null);
    },
    [onAnalyser],
  );
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
      const ctx = (audio.current ??= new AudioContext());
      await ctx.resume();
      const node = ctx.createAnalyser();
      node.fftSize = 1024;
      node.smoothingTimeConstant = 0.8;
      ctx.createMediaElementSource(a).connect(node);
      node.connect(ctx.destination);
      onAnalyser(node);
      await new Promise<void>((done, fail) => {
        a.onended = () => done();
        a.onerror = () => fail(new Error("The preview could not be played."));
        a.play().catch(fail);
      });
      URL.revokeObjectURL(url);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      onAnalyser(null);
      setPlaying("");
    }
  };
  const remove = async () => {
    await api(`/api/streamers/${me.id}/voice`, { method: "DELETE" }).catch((e) => setErr((e as Error).message));
    onChange({ ...me, voice: null });
  };
  const score = v.ref_score;
  const langs = me.default_langs.filter((c) => c !== "en-IN");
  return (
    <section className="card rise space-y-6 p-5 sm:p-8" aria-labelledby="vc-h">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="vc-h" className="eyebrow flex items-center gap-2"><Check aria-hidden className="size-3.5 text-ok" />@{me.handle}: your voice is ready</h2>
        <button onClick={remove} className="inline-flex items-center gap-2 text-sm text-muted hover:text-fg"><Trash2 aria-hidden className="size-4" />Delete my voice</button>
      </div>
      <div className="flex flex-col items-center gap-6 sm:flex-row">
        <Ring value={score ?? 0} size={132} hue={score == null ? "var(--line)" : score >= 0.7 ? "var(--ok)" : "var(--hi)"}>
          <div className="text-center">
            <p className="tnum font-mono text-3xl font-medium">{score == null ? "n/a" : `${Math.round(score * 100)}%`}</p>
            <p className="text-[11px] text-muted">understood</p>
          </div>
        </Ring>
        <div className="min-w-0 flex-1">
          <p className="text-sm text-muted">
            {score == null
              ? "The copy was made but not tested, because the fast voice engine was not reachable."
              : "Your copied voice spoke a known sentence and speech recognition heard it back. This is the share of words it got. It says the voice is clear, not how much it sounds like you: use your ears for that."}
          </p>
          <dl className="mt-4 grid grid-cols-3 gap-3 text-sm">
            <div className="rounded-panel border border-line bg-sunken p-3"><dt className="text-xs text-muted">Sample used</dt><dd className="tnum mt-1 font-mono text-lg">{v.ref_seconds != null ? `${v.ref_seconds} s` : "none"}</dd></div>
            <div className="rounded-panel border border-line bg-sunken p-3"><dt className="text-xs text-muted">Made in</dt><dd className="tnum mt-1 font-mono text-lg">{v.ref_build_s != null ? `${v.ref_build_s} s` : "n/a"}</dd></div>
            <div className="rounded-panel border border-line bg-sunken p-3"><dt className="text-xs text-muted">Consent</dt><dd className="mt-1 text-xs leading-tight">{new Date(v.consent_at).toLocaleString()}</dd></div>
          </dl>
        </div>
      </div>
      {!v.gpu_voice && <Notice tone="warn">The fast voice engine was not reachable, so only the slower copy was made. Live, the first language uses it and the others use stock voices.</Notice>}
      {score != null && score < 0.7 && <Notice tone="warn">This recording did not make a clear voice. A quieter room and steady talking usually fix it: delete and record again.</Notice>}
      <div className="border-t border-line pt-5">
        <p className="font-medium">Hear yourself</p>
        <p className="mt-1 text-sm text-muted">Each button makes a fresh line in your voice. The time shown is how long this one took to arrive.</p>
        <div className="mt-3 flex flex-wrap gap-2.5">
          {langs.length ? langs.map((c) => (
            <button key={c} onClick={() => preview(c)} disabled={!!playing} className={`inline-flex h-11 items-center gap-2.5 rounded-chip border px-4 text-[0.95rem] transition-colors disabled:opacity-50 ${playing === c ? "border-fg bg-fg text-on-fg disabled:opacity-100" : "border-line bg-surface hover:border-fg"}`}>
              {playing === c ? <span aria-hidden className="pulse-dot size-2 rounded-full bg-current" /> : <Play aria-hidden className="size-4" />}
              <span aria-hidden className="size-2 rounded-full" style={{ background: lang(c).hue }} />
              {lang(c).name}
              {timing[c] && playing !== c && <span className="tnum font-mono text-xs text-muted">{timing[c]}</span>}
            </button>
          )) : <p className="text-sm text-muted">English uses the slower copy or a stock voice, so there is no fast preview for it.</p>}
        </div>
      </div>
      {err && <Notice tone="error" role="alert">{err}</Notice>}
    </section>
  );
}

function GoLive({ me, onAnalyser, health }: { me: Streamer; onAnalyser: SetAnalyser; health: EngineHealth | null }) {
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [device, setDevice] = useState("");
  const [an, setAn] = useState<AnalyserNode | null>(null);
  const [yt, setYt] = useState("");
  const [langs, setLangs] = useState<string[]>(me.default_langs);
  const [mode, setMode] = useState<"clone" | "stock">("clone");
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
  }, [listDevices]);

  // The chosen input, exactly as it will be sent (no filters), shown on the bars here and on the orb beside.
  useEffect(() => {
    if (!device) return;
    let stop = false;
    let stream: MediaStream | null = null;
    let ctx: AudioContext | null = null;
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: { deviceId: { exact: device }, echoCancellation: false, noiseSuppression: false, autoGainControl: false } });
        if (stop) return stream.getTracks().forEach((t) => t.stop());
        ctx = new AudioContext();
        const node = ctx.createAnalyser();
        node.fftSize = 1024;
        node.smoothingTimeConstant = 0.8;
        ctx.createMediaStreamSource(stream).connect(node);
        setAn(node);
        onAnalyser(node);
      } catch {
        setAn(null);
        onAnalyser(null);
      }
    })();
    return () => {
      stop = true;
      stream?.getTracks().forEach((t) => t.stop());
      void ctx?.close();
      setAn(null);
      onAnalyser(null);
    };
  }, [device, onAnalyser]);

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
  const input = devices.find((d) => d.deviceId === device)?.label || "Audio input";
  const ready: [string, boolean][] = [
    [mode === "clone" ? "My own voice" : "Stock voices", true],
    [`${langs.length} ${langs.length === 1 ? "language" : "languages"}`, langs.length > 0],
    [device ? input : "No input", Boolean(device)],
    [yt.trim() ? "YouTube linked" : "No video: dub and captions only", true],
  ];
  return (
    <section className="card card-lift rise space-y-8 p-5 sm:p-8" aria-labelledby="g-h" style={{ animationDelay: "0.06s" }}>
      <h2 id="g-h" className="h-display text-[1.9rem] leading-tight sm:text-[2.3rem]">Ready to <em>go live</em></h2>

      <div>
        <label className="block">
          <span className="text-lg font-medium tracking-[-0.01em]">Where your voice comes from</span>
          <select value={device} onChange={(e) => setDevice(e.target.value)} className="input mt-3">
            {devices.map((d) => <option key={d.deviceId} value={d.deviceId}>{d.label || "Audio input"}</option>)}
          </select>
        </label>
        <div className="mt-3 flex items-center gap-4 rounded-panel bg-sunken p-4">
          <VoiceOrb size={52} analyser={an} className="shrink-0" />
          <VoiceBars analyser={an} active={false} bars={40} height={44} colors={["--hi"]} />
        </div>
        <p className="mt-2 text-sm text-muted">Speak: the bars should move. Use the same mic as in OBS. To dub a recording instead, pick a virtual cable (for example CABLE Output) that carries its sound.</p>
      </div>

      <label className="block">
        <span className="flex items-center gap-2 text-lg font-medium tracking-[-0.01em]"><MonitorPlay aria-hidden className="size-5" />Your YouTube live link</span>
        <input value={yt} onChange={(e) => setYt(e.target.value)} placeholder="https://youtube.com/live/…" className="input mt-3" />
        <span className="mt-2 block text-sm text-muted">In YouTube Studio set Stream latency to Low latency. Without a link, viewers get the dub and captions only.</span>
      </label>

      <LangPicker langs={langs} toggle={toggle} label="Languages for this stream" />

      <fieldset>
        <legend className="text-lg font-medium tracking-[-0.01em]">Voice</legend>
        <div className="mt-3 grid gap-2.5 sm:grid-cols-2">
          {(["clone", "stock"] as const).map((m) => (
            <button key={m} type="button" role="radio" aria-checked={mode === m} onClick={() => setMode(m)}
              className={`rounded-panel border p-4 text-left transition-colors ${mode === m ? "border-fg bg-sunken" : "border-line hover:border-fg/50"}`}>
              <span className="flex items-center justify-between gap-2 font-medium">
                {m === "clone" ? "My own voice" : "Stock voices"}
                <span className={`grid size-5 place-items-center rounded-full border ${mode === m ? "border-fg bg-fg text-on-fg" : "border-line"}`}>{mode === m && <Check aria-hidden className="size-3" />}</span>
              </span>
              <span className="mt-1 block text-sm text-muted">{m === "clone" ? "The voice you recorded, from your first phrase." : "A ready-made voice for each language."}</span>
            </button>
          ))}
        </div>
        {mode === "clone" && langs.includes("en-IN") && <p className="mt-2 text-sm text-muted">English uses the slower copy of your voice or a stock voice; the other languages use the fast engine.</p>}
      </fieldset>

      {health && mode === "clone" && enginesUp === 0 && <Notice tone="warn">The fast voice engines are not reachable. You can still go live: your first language uses the slower copy of your voice, the others stock voices.</Notice>}
      {err && <Notice tone="error" role="alert">{err}</Notice>}

      <div className="border-t border-line pt-6">
        <ul className="flex flex-wrap gap-2 text-sm">
          {ready.map(([label, ok]) => (
            <li key={label} className="inline-flex max-w-full items-center gap-2 rounded-chip border border-line bg-surface px-3 py-1.5">
              {ok ? <Check aria-hidden className="size-3.5 shrink-0 text-ok" /> : <CircleAlert aria-hidden className="size-3.5 shrink-0 text-danger" />}
              <span className="truncate">{label}</span>
            </li>
          ))}
        </ul>
        <div className="mt-5 flex flex-wrap items-center gap-5">
          <Button variant="danger" size="lg" onClick={go} disabled={busy || !langs.length || !device}><Radio aria-hidden className="size-5" />{busy ? "Starting…" : "Open my live console"}</Button>
          <p className="flex items-center gap-2 text-sm text-muted">
            <Headphones aria-hidden className="size-4 shrink-0" />
            Wear headphones so the dub does not leak into your mic.
          </p>
        </div>
      </div>
    </section>
  );
}
