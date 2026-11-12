"use client";
import { useCallback, useEffect, useState } from "react";
import { Nav } from "@/components/layout/Nav";
import { Button } from "@/components/ui/Button";
import { LanguageChip } from "@/components/ui/LanguageChip";
import { DelayBadge } from "@/components/ui/DelayBadge";
import { Sparkline } from "@/components/ui/Sparkline";
import { ChatList, useChat } from "@/components/live/ChatFeed";
import { useAudioLevel } from "@/components/voice/useAudioLevel";
import { API_BASE, api, type LiveSession, type VoiceProfile } from "@/lib/api";
import { startMicIngest, type MicIngest } from "@/lib/micIngest";
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
  const save = (s: Saved | null) => {
    setSaved(s);
    try {
      if (s) localStorage.setItem(KEY, JSON.stringify(s));
      else localStorage.removeItem(KEY);
    } catch {
      /* storage blocked */
    }
  };
  return (
    <div className="theme-dark min-h-dvh bg-bg text-fg">
      <Nav />
      {saved ? <Console sid={saved.sid} token={saved.token} onNew={() => save(null)} /> : <CreateForm onCreated={save} />}
    </div>
  );
}

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
    <main className="mx-auto max-w-2xl px-4 py-12 sm:px-8 sm:py-16">
      <h1 className="font-display text-[clamp(2rem,5vw,3rem)] font-semibold leading-tight">Go live in every language</h1>
      <p className="mt-3 text-slate">Stream on YouTube as usual. Your viewers open your Bharat Dub link and hear you dubbed live.</p>
      <label className="mt-10 block">
        <span className="font-display text-lg font-semibold">YouTube live link or video id</span>
        <input value={yt} onChange={(e) => setYt(e.target.value)} placeholder="https://youtube.com/live/…" className="mt-2 h-12 w-full rounded-panel border border-mist bg-surface px-4" />
        <span className="mt-1 block text-sm text-slate">Optional. Without it, viewers get audio and captions only.</span>
      </label>
      <fieldset className="mt-8">
        <legend className="font-display text-lg font-semibold">Languages for viewers (up to 4)</legend>
        <div className="mt-3 flex flex-wrap gap-2.5">
          {TARGET_LANGS.map((l) => <LanguageChip key={l.code} code={l.code} selected={langs.includes(l.code)} onClick={() => toggle(l.code)} />)}
        </div>
      </fieldset>
      <label className="mt-8 block">
        <span className="font-display text-lg font-semibold">Voice</span>
        <select value={voice} onChange={(e) => setVoice(e.target.value)} className="mt-2 h-12 w-full rounded-panel border border-mist bg-surface px-3">
          <option value="">Stock voice per language</option>
          {voices.map((v) => <option key={v.id} value={v.id}>{v.display_name} (my cloned voice)</option>)}
        </select>
      </label>
      {err && <p role="alert" className="mt-6 rounded-panel border border-[var(--bn)] px-4 py-3 text-sm">{err}</p>}
      <Button size="lg" className="mt-10" disabled={!langs.length || busy} onClick={create}>{busy ? "Creating…" : "Create session"}</Button>
      <p className="mt-6 text-sm text-slate">Wear headphones while streaming so the dub does not leak into your mic.</p>
    </main>
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
  const level = useAudioLevel(mic?.source ?? null, mic?.ctx ?? null);
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
  const viewer = `${origin}/watch/${sid}`;
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

  return (
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-semibold">Live console</h1>
          <p className="mt-1 text-sm text-slate">
            {langs.map((c) => lang(c).name).join(" · ")} · {session?.viewers ?? 0} listening
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <DelayBadge ms={feed.stats?.p50_ms} label="Median delay" />
          {feed.stats?.p95_ms != null && <span className="tnum text-sm text-slate">p95 {(feed.stats.p95_ms / 1000).toFixed(1)} s</span>}
          {isLive ? (
            <Button variant="secondary" onClick={stop}>Stop</Button>
          ) : (
            <button onClick={goLive} disabled={micState === "connecting"} className="relative h-14 rounded-chip bg-[var(--bn)] px-8 font-display text-lg font-semibold text-white disabled:opacity-60">
              {micState === "connecting" ? "Connecting…" : "Go live"}
            </button>
          )}
        </div>
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-2 text-sm">
        <button onClick={() => copy(viewer, "viewer")} className="rounded-chip border border-mist px-4 py-2 hover:border-fg">{copied === "viewer" ? "Copied" : "Copy viewer link"}</button>
        <a href={`/watch/${sid}`} target="_blank" className="rounded-chip border border-mist px-4 py-2 hover:border-fg">Open viewer</a>
        <a href={`/watch/${sid}?demo=1`} target="_blank" className="rounded-chip border border-mist px-4 py-2 hover:border-fg">Stage demo view</a>
        <button onClick={() => copy(`${origin}/overlay/${sid}`, "overlay")} className="rounded-chip border border-mist px-4 py-2 hover:border-fg">{copied === "overlay" ? "Copied" : "Copy OBS overlay link"}</button>
        <button onClick={onNew} className="ml-auto text-slate underline-offset-4 hover:text-fg hover:underline">New session</button>
      </div>

      {errors.length > 0 && (
        <ul className="mt-4 space-y-1 text-sm" role="status">
          {errors.map((e, i) => <li key={i} className="rounded-panel border border-[var(--hi)] px-3 py-2">{e}</li>)}
        </ul>
      )}

      <div className="mt-8 grid gap-6 lg:grid-cols-[1fr_1fr_320px]">
        <section className="rounded-panel border border-mist p-5" aria-labelledby="src-h">
          <div className="flex items-center justify-between">
            <h2 id="src-h" className="font-display font-semibold">You said</h2>
            <span className="flex items-center gap-2 text-sm text-slate">
              <span aria-hidden className="relative grid size-6 place-items-center">
                <span className="absolute inset-0 rounded-full bg-[var(--hi)] opacity-30" style={{ transform: `scale(${0.4 + level * 1.4})` }} />
                <span className={`size-2.5 rounded-full ${speaking || level > 0.08 ? "bg-[var(--hi)]" : "bg-slate"}`} />
              </span>
              {isLive ? (speaking ? "Hearing you" : "Listening") : "Mic off"}
            </span>
          </div>
          <ul className="mt-4 max-h-[420px] space-y-2 overflow-y-auto" lang="hi">
            {transcript.length ? transcript.slice().reverse().map((t, i) => <li key={`${t.t}-${i}`} className={i ? "text-slate" : ""}>{t.text}</li>) : <li className="text-sm text-slate">Press Go live and speak. Or stream from the mic client (below).</li>}
          </ul>
        </section>

        <section className="grid gap-4" aria-label="Captions per language">
          {langs.map((c) => {
            const caps = feed.captions.filter((x) => x.lang === c).slice(-3).reverse();
            return (
              <div key={c} className="rounded-panel border border-mist p-4">
                <h2 className="flex items-center gap-2 font-display font-semibold"><span className="size-2.5 rounded-full" style={{ background: lang(c).hue }} />{lang(c).name}</h2>
                <ul className="mt-2 space-y-1.5" lang={lang(c).short}>
                  {caps.length ? caps.map((x, i) => (
                    <li key={x.seq} className={i ? "text-sm text-slate" : "border-b-2 pb-1"} style={i ? undefined : { borderColor: lang(c).hue }}>{x.text}</li>
                  )) : <li className="text-sm text-slate">Waiting for speech</li>}
                </ul>
              </div>
            );
          })}
        </section>

        <aside className="grid content-start gap-6">
          <section className="rounded-panel border border-mist p-4">
            <h2 className="font-display font-semibold">Delay, last 60 chunks</h2>
            <p className="text-xs text-slate">{langs[0] ? `${lang(langs[0]).name}: speech end to first dubbed audio` : ""}</p>
            <div className="mt-3"><Sparkline values={recent} /></div>
          </section>
          <section className="rounded-panel border border-mist p-4">
            <h2 className="font-display font-semibold">Chat, translated for you</h2>
            <div className="mt-3 max-h-72 overflow-y-auto"><ChatList msgs={chat.msgs} /></div>
          </section>
        </aside>
      </div>

      <details className="mt-10 rounded-panel border border-mist p-5">
        <summary className="cursor-pointer font-display font-semibold">Stream from the desktop mic client instead</summary>
        <p className="mt-3 text-sm text-slate">Useful when your streaming PC is a different machine. Keep this token private.</p>
        <pre className="mt-3 overflow-x-auto rounded-panel bg-surface p-4 text-sm">{`cd ingest_client
python client.py --server ${API_BASE.replace(/^http/, "ws")} --session ${sid} --token ${token}`}</pre>
      </details>
    </main>
  );
}
