"use client";
import { useCallback, useEffect, useState } from "react";
import { ArrowRight, Captions, Check, Copy, ExternalLink, Headphones, MessagesSquare, Mic, MonitorPlay, Plus, Presentation, Radio, Square, Terminal, Timer, Users } from "lucide-react";
import { Shell } from "@/components/layout/Shell";
import { Button } from "@/components/ui/Button";
import { DelayBadge } from "@/components/ui/DelayBadge";
import { LanguageChip } from "@/components/ui/LanguageChip";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { Sparkline } from "@/components/ui/Sparkline";
import { ChatList, useChat } from "@/components/live/ChatFeed";
import { VoiceBars } from "@/components/voice/VoiceBars";
import { VoiceOrb } from "@/components/voice/VoiceOrb";
import { API_BASE, api, type LiveSession, type VoiceProfile } from "@/lib/api";
import { startMicIngest, type MicIngest } from "@/lib/micIngest";
import { useAnalyser } from "@/lib/useMic";
import { useLiveFeed } from "@/lib/useLiveFeed";
import { TARGET_LANGS, lang } from "@/lib/langs";

const KEY = "bd-live-session";

interface Saved {
  sid: string;
  token: string;
}

export default function LivePage() {
  const [saved, setSaved] = useState<Saved | null>(null);
  useEffect(() => {
    try {
      const raw = localStorage.getItem(KEY);
      if (raw) setSaved(JSON.parse(raw));
    } catch {
      /* storage blocked */
    }
  }, []);
  const save = useCallback((s: Saved | null) => {
    setSaved(s);
    try {
      if (s) localStorage.setItem(KEY, JSON.stringify(s));
      else localStorage.removeItem(KEY);
    } catch {
      /* storage blocked */
    }
  }, []);
  const onNew = useCallback(() => save(null), [save]);
  return (
    <Shell dark>
      {saved ? <Console sid={saved.sid} token={saved.token} onNew={onNew} /> : <CreateForm onCreated={save} />}
    </Shell>
  );
}

const HOW = [
  { icon: MonitorPlay, text: "Stream on YouTube exactly as you do today." },
  { icon: Users, text: "Share your Bharat Dub link. Viewers pick a language." },
  { icon: Captions, text: "They hear you dubbed, with live captions." },
  { icon: MessagesSquare, text: "Their chat reaches you translated." },
];

function CreateForm({ onCreated }: { onCreated: (s: Saved) => void }) {
  const [yt, setYt] = useState("");
  const [langs, setLangs] = useState<string[]>(["ta-IN", "bn-IN", "en-IN"]);
  const [voices, setVoices] = useState<VoiceProfile[]>([]);
  const [voice, setVoice] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api<VoiceProfile[]>("/api/voices").then(setVoices).catch(() => {});
  }, []);
  const toggle = (c: string) => setLangs((l) => (l.includes(c) ? l.filter((x) => x !== c) : l.length >= 4 ? l : [...l, c]));
  const create = async () => {
    setBusy(true);
    setErr("");
    try {
      const r = await api<{ session_id: string; ingest_token: string }>("/api/live/sessions", {
        method: "POST",
        body: JSON.stringify({ youtube_video_id: yt, target_langs: langs, voice_profile_id: voice || null }),
      });
      onCreated({ sid: r.session_id, token: r.ingest_token });
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  };
  return (
    <div className="mx-auto max-w-6xl px-5 pb-24 pt-12 sm:px-8 sm:pt-16">
      <PageHeader icon={Radio} eyebrow="Live" title={<>Go live in <em>every language</em></>} lede="Stream on YouTube as usual. Your viewers open your Bharat Dub link and hear you dubbed while you speak." />
      <div className="mt-12 grid gap-8 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <div className="card card-lift rise space-y-8 p-5 sm:p-8">
          <label className="block">
            <span className="text-lg font-medium tracking-[-0.01em]">YouTube live link or video id</span>
            <input value={yt} onChange={(e) => setYt(e.target.value)} placeholder="https://youtube.com/live/…" className="input mt-3" />
            <span className="mt-2 block text-sm text-muted">Optional. Without it, viewers get audio and captions only.</span>
          </label>
          <fieldset>
            <legend className="text-lg font-medium tracking-[-0.01em]">Languages for viewers <span className="text-sm font-normal text-muted">up to 4</span></legend>
            <div className="mt-3 flex flex-wrap gap-2.5">
              {TARGET_LANGS.map((l) => <LanguageChip key={l.code} code={l.code} selected={langs.includes(l.code)} onClick={() => toggle(l.code)} />)}
            </div>
          </fieldset>
          <label className="block">
            <span className="text-lg font-medium tracking-[-0.01em]">Voice</span>
            <select value={voice} onChange={(e) => setVoice(e.target.value)} className="input mt-3">
              <option value="">Stock voice per language</option>
              {voices.map((v) => <option key={v.id} value={v.id}>{v.display_name} (my cloned voice)</option>)}
            </select>
          </label>
          {err && <Notice tone="error" role="alert">{err}</Notice>}
          <div className="flex flex-wrap items-center gap-5">
            <Button size="lg" disabled={!langs.length || busy} onClick={create}>
              {busy ? "Creating…" : "Create session"}
              <ArrowRight aria-hidden className="size-4 transition-transform group-hover:translate-x-0.5" />
            </Button>
            <p className="flex items-center gap-2 text-sm text-muted">
              <Headphones aria-hidden className="size-4 shrink-0" />
              Wear headphones so the dub does not leak into your mic.
            </p>
          </div>
        </div>

        <aside className="card rise relative overflow-hidden p-6 sm:p-8" style={{ animationDelay: "0.08s" }}>
          <div className="flex justify-center py-4">
            <VoiceOrb size={170} />
          </div>
          <h2 className="eyebrow mt-6">How a live session works</h2>
          <ol className="mt-5 space-y-4">
            {HOW.map((h, i) => (
              <li key={h.text} className="flex items-start gap-3.5">
                <span className="grid size-10 shrink-0 place-items-center rounded-[12px] border border-line bg-bg">
                  <h.icon aria-hidden className="size-[18px]" />
                </span>
                <span className="pt-1.5">
                  <span className="tnum mr-2 font-mono text-xs text-muted">0{i + 1}</span>
                  {h.text}
                </span>
              </li>
            ))}
          </ol>
        </aside>
      </div>
    </div>
  );
}

function Console({ sid, token, onNew }: { sid: string; token: string; onNew: () => void }) {
  const [info, setInfo] = useState<LiveSession | null>(null);
  const [transcript, setTranscript] = useState<{ text: string; t: number }[]>([]);
  const [speaking, setSpeaking] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [mic, setMic] = useState<MicIngest | null>(null);
  const [micState, setMicState] = useState<string>("off");
  const [recent, setRecent] = useState<number[]>([]);
  const [copied, setCopied] = useState("");
  const onEvent = useCallback((m: Record<string, unknown>) => {
    if (m.type === "transcript") setTranscript((t) => [...t, { text: String(m.text), t: Number(m.t_ms) }].slice(-30));
    else if (m.type === "vad") setSpeaking(Boolean(m.speaking));
    else if (m.type === "error") setErrors((e) => [String(m.message), ...e].slice(0, 3));
  }, []);
  const feed = useLiveFeed(sid, "*", { audioOn: false, offsetMs: 0, onEvent });
  const chat = useChat(sid, "hi-IN");
  const analyser = useAnalyser(mic?.source ?? null, mic?.ctx ?? null);
  const session = feed.session ?? info;

  useEffect(() => {
    api<LiveSession>(`/api/live/sessions/${sid}`).then(setInfo).catch(() => onNew());
  }, [sid, onNew]);
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const m = await api<{ per_lang: Record<string, { recent_ms: number[] }> }>(`/api/live/sessions/${sid}/metrics`);
        const first = session?.target_langs[0];
        if (first && m.per_lang[first]) setRecent(m.per_lang[first].recent_ms);
      } catch {
        /* backend away */
      }
    }, 3000);
    return () => clearInterval(id);
  }, [sid, session?.target_langs]);
  useEffect(() => () => mic?.stop(), [mic]);

  const goLive = async () => {
    try {
      const m = await startMicIngest(sid, token, (s, d) => {
        setMicState(s);
        if (d) setErrors((e) => [d, ...e].slice(0, 3));
      });
      setMic(m);
    } catch (e) {
      setMicState("error");
      setErrors((x) => [`Microphone: ${(e as Error).message}`, ...x].slice(0, 3));
    }
  };
  const stop = async () => {
    mic?.stop();
    setMic(null);
    setMicState("off");
    await api(`/api/live/sessions/${sid}/stop`, { method: "POST" }).catch(() => {});
  };
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const copy = async (text: string, what: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(what);
      setTimeout(() => setCopied(""), 1800);
    } catch {
      /* clipboard blocked */
    }
  };
  const langs = session?.target_langs ?? [];
  const isLive = micState === "live";
  const tool = "inline-flex h-10 items-center gap-2 rounded-chip border border-line bg-surface px-4 text-sm transition-colors hover:border-fg";

  return (
    <div className="mx-auto max-w-7xl px-5 pb-24 pt-10 sm:px-8">
      <header className="rise flex flex-wrap items-end justify-between gap-6">
        <div>
          <p className="eyebrow inline-flex items-center gap-2 rounded-chip border border-line bg-surface/70 px-3 py-1.5">
            <span className={`size-2 rounded-full ${isLive ? "pulse-dot bg-danger" : "bg-muted"}`} />
            {isLive ? "On air" : "Off air"}
          </p>
          <h1 className="h-display mt-5 text-[clamp(2.4rem,5vw,3.75rem)]">Live <em>console</em></h1>
          <ul className="mt-4 flex flex-wrap items-center gap-2 text-sm">
            {langs.map((c) => (
              <li key={c} className="inline-flex items-center gap-2 rounded-chip border border-line bg-surface px-3 py-1.5">
                <span className="size-2 rounded-full" style={{ background: lang(c).hue }} />
                {lang(c).name}
              </li>
            ))}
            <li className="inline-flex items-center gap-2 px-2 text-muted">
              <Users aria-hidden className="size-4" />
              <span className="tnum">{session?.viewers ?? 0}</span> listening
            </li>
          </ul>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <DelayBadge ms={feed.stats?.p50_ms} label="Median delay" />
          {feed.stats?.p95_ms != null && <span className="tnum font-mono text-xs text-muted">p95 {(feed.stats.p95_ms / 1000).toFixed(1)} s</span>}
          {isLive ? (
            <Button variant="secondary" size="lg" onClick={stop}>
              <Square aria-hidden className="size-4 fill-current" />
              Stop
            </Button>
          ) : (
            <Button variant="danger" size="lg" onClick={goLive} disabled={micState === "connecting"}>
              <Radio aria-hidden className="size-5" />
              {micState === "connecting" ? "Connecting…" : "Go live"}
            </Button>
          )}
        </div>
      </header>

      <div className="mt-7 flex flex-wrap items-center gap-2">
        <button onClick={() => copy(`${origin}/watch/${sid}`, "viewer")} className={tool}>
          {copied === "viewer" ? <Check aria-hidden className="size-4 text-ok" /> : <Copy aria-hidden className="size-4" />}
          {copied === "viewer" ? "Copied" : "Copy viewer link"}
        </button>
        <a href={`/watch/${sid}`} target="_blank" className={tool}><ExternalLink aria-hidden className="size-4" />Open viewer</a>
        <a href={`/watch/${sid}?demo=1`} target="_blank" className={tool}><Presentation aria-hidden className="size-4" />Stage demo view</a>
        <button onClick={() => copy(`${origin}/overlay/${sid}`, "overlay")} className={tool}>
          {copied === "overlay" ? <Check aria-hidden className="size-4 text-ok" /> : <Copy aria-hidden className="size-4" />}
          {copied === "overlay" ? "Copied" : "Copy OBS overlay link"}
        </button>
        <button onClick={onNew} className="ml-auto inline-flex h-10 items-center gap-2 rounded-chip px-3 text-sm text-muted hover:text-fg">
          <Plus aria-hidden className="size-4" />
          New session
        </button>
      </div>

      {errors.length > 0 && (
        <ul className="mt-5 space-y-2">
          {errors.map((e, i) => <li key={i}><Notice tone="warn">{e}</Notice></li>)}
        </ul>
      )}

      <div className="mt-8 grid gap-5 lg:grid-cols-[1fr_1fr_340px]">
        <section className="card flex flex-col p-5 sm:p-6 lg:self-start" aria-labelledby="src-h">
          <div className="flex items-center justify-between">
            <h2 id="src-h" className="eyebrow flex items-center gap-2"><Mic aria-hidden className="size-3.5" />You said</h2>
            <span className="text-sm text-muted">{isLive ? (speaking ? "Hearing you" : "Listening") : "Mic off"}</span>
          </div>
          <div className="mt-4 flex items-center gap-4 rounded-panel bg-sunken p-4">
            <VoiceOrb size={64} analyser={analyser} className="shrink-0" />
            <VoiceBars analyser={analyser} active={false} bars={36} height={48} colors={["--hi"]} />
          </div>
          <ul className="mt-5 max-h-[400px] flex-1 space-y-2.5 overflow-y-auto font-indic text-lg" lang="hi" data-lenis-prevent>
            {transcript.length ? (
              transcript.slice().reverse().map((t, i) => <li key={`${t.t}-${i}`} className={i ? "text-base text-muted" : "font-medium"}>{t.text}</li>)
            ) : (
              <li className="font-sans text-sm text-muted">Press Go live and speak. Or stream from the desktop mic client, below.</li>
            )}
          </ul>
        </section>

        <section className="grid content-start gap-5" aria-label="Captions per language">
          {langs.map((c) => {
            const caps = feed.captions.filter((x) => x.lang === c).slice(-3).reverse();
            return (
              <div key={c} className="card relative overflow-hidden p-5">
                <span aria-hidden className="absolute inset-y-0 left-0 w-1" style={{ background: lang(c).hue }} />
                <h2 className="eyebrow flex items-center gap-2"><span className="size-2 rounded-full" style={{ background: lang(c).hue }} />{lang(c).name}</h2>
                <ul className="mt-3 space-y-1.5 font-indic" lang={lang(c).short}>
                  {caps.length ? caps.map((x, i) => <li key={x.seq} className={i ? "text-sm text-muted" : "text-lg font-medium leading-snug"}>{x.text}</li>) : <li className="font-sans text-sm text-muted">Waiting for speech</li>}
                </ul>
              </div>
            );
          })}
        </section>

        <aside className="grid content-start gap-5">
          <section className="card p-5">
            <h2 className="eyebrow flex items-center gap-2"><Timer aria-hidden className="size-3.5" />Delay, last 60 chunks</h2>
            <p className="mt-1.5 text-xs text-muted">{langs[0] ? `${lang(langs[0]).name}: speech end to first dubbed audio` : ""}</p>
            <div className="mt-4"><Sparkline values={recent} /></div>
          </section>
          <section className="card p-5">
            <h2 className="eyebrow flex items-center gap-2"><MessagesSquare aria-hidden className="size-3.5" />Chat, translated for you</h2>
            <div className="mt-4 max-h-72 overflow-y-auto" data-lenis-prevent><ChatList msgs={chat.msgs} /></div>
          </section>
        </aside>
      </div>

      <details className="card mt-8 p-5 sm:p-6">
        <summary className="flex cursor-pointer items-center gap-2.5 font-medium"><Terminal aria-hidden className="size-4" />Stream from the desktop mic client instead</summary>
        <p className="mt-3 text-sm text-muted">Useful when your streaming PC is a different machine. Keep this token private.</p>
        <pre className="mt-3 overflow-x-auto rounded-panel bg-sunken p-4 font-mono text-sm" data-lenis-prevent>{`cd ingest_client
python client.py --server ${API_BASE.replace(/^http/, "ws")} --session ${sid} --token ${token}`}</pre>
      </details>
    </div>
  );
}
