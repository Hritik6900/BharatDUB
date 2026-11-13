"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { WS_BASE, type LiveSession } from "./api";

export interface Caption {
  seq: number;
  lang: string;
  text: string;
  t_speech_ms: number;
  untranslated?: boolean;
}
export interface Stats {
  p50_ms: number | null;
  p95_ms: number | null;
  n: number;
}

const JITTER_S = 0.3;
// Dubbed speech can run longer than the original. When more than CATCHUP_AFTER_S of audio is waiting, play a little
// faster; a chunk that would start more than MAX_BACKLOG_S late is skipped (its caption still shows).
const CATCHUP_AFTER_S = 2;
const CATCHUP_RATE = 1.1;
const MAX_BACKLOG_S = 10;

/**
 * Subscribes to /ws/watch/{sid}?lang=. Captions always; audio is decoded and scheduled back-to-back
 * with a 300 ms jitter buffer plus `offsetMs` (sync with the YouTube player) when `audioOn`.
 */
export function useLiveFeed(sid: string, langCode: string, opts: { audioOn: boolean; offsetMs: number; onEvent?: (m: Record<string, unknown>) => void }) {
  const [captions, setCaptions] = useState<Caption[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [session, setSession] = useState<LiveSession | null>(null);
  const [connected, setConnected] = useState(false);
  const ctxRef = useRef<AudioContext | null>(null);
  const nextAt = useRef(0);
  const cur = useRef({ seq: -1, drop: false, rate: 1 });
  const optsRef = useRef(opts);
  optsRef.current = opts;

  // The dubbed audio passes through this analyser on its way out, so the page can draw what is really playing.
  const [analyser, setAnalyser] = useState<AnalyserNode | null>(null);
  const outRef = useRef<AudioNode | null>(null);

  const ensureAudio = useCallback(async () => {
    if (!ctxRef.current) {
      const ctx = new AudioContext();
      const an = ctx.createAnalyser();
      an.fftSize = 1024;
      an.smoothingTimeConstant = 0.8;
      an.connect(ctx.destination);
      ctxRef.current = ctx;
      outRef.current = an;
      setAnalyser(an);
    }
    if (ctxRef.current.state === "suspended") await ctxRef.current.resume();
    return ctxRef.current;
  }, []);

  useEffect(() => {
    if (!sid || !langCode) return;
    let ws: WebSocket | null = null;
    let closed = false;
    let retry: ReturnType<typeof setTimeout>;
    setCaptions([]);
    nextAt.current = 0;

    const connect = () => {
      ws = new WebSocket(`${WS_BASE}/ws/watch/${sid}?lang=${encodeURIComponent(langCode)}`);
      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (!closed) retry = setTimeout(connect, 1500);
      };
      ws.onmessage = (ev) => {
        const m = JSON.parse(ev.data);
        optsRef.current.onEvent?.(m);
        if (m.type === "hello") {
          setSession(m.session);
          if (m.stats) setStats(m.stats);
        } else if (m.type === "session") setSession(m);
        else if (m.type === "stats") setStats(m);
        else if (m.type === "caption") {
          const delay = m.history ? 0 : Math.max(0, optsRef.current.offsetMs);
          // Keep the last 12 captions per language (a global cap would starve the languages that arrive first).
          const add = () =>
            setCaptions((c) => {
              const rest = c.filter((x) => !(x.seq === m.seq && x.lang === m.lang));
              const same = rest.filter((x) => x.lang === m.lang);
              const drop = new Set(same.slice(0, Math.max(0, same.length - 11)));
              return [...rest.filter((x) => !drop.has(x)), m];
            });
          if (delay) setTimeout(add, delay);
          else add();
        } else if (m.type === "audio" && m.pcm_b64 && optsRef.current.audioOn) {
          schedule(m.pcm_b64, m.sample_rate, m.seq);
        }
      };
    };

    const schedule = (b64: string, rate: number, seq: number) => {
      const ctx = ctxRef.current;
      if (!ctx || ctx.state !== "running") return;
      if (seq !== cur.current.seq) {
        // Decide once per chunk, so a sentence is never cut or sped up halfway.
        const backlog = Math.max(0, nextAt.current - ctx.currentTime);
        cur.current = { seq, drop: backlog > MAX_BACKLOG_S, rate: backlog > CATCHUP_AFTER_S ? CATCHUP_RATE : 1 };
      }
      if (cur.current.drop) return;
      const bin = atob(b64);
      const n = bin.length >> 1;
      const buf = ctx.createBuffer(1, n, rate);
      const ch = buf.getChannelData(0);
      for (let i = 0; i < n; i++) {
        const lo = bin.charCodeAt(2 * i);
        const hi = bin.charCodeAt(2 * i + 1);
        let v = (hi << 8) | lo;
        if (v >= 0x8000) v -= 0x10000;
        ch[i] = v / 0x8000;
      }
      const earliest = ctx.currentTime + JITTER_S + Math.max(0, optsRef.current.offsetMs) / 1000;
      const at = nextAt.current > ctx.currentTime ? Math.max(nextAt.current, ctx.currentTime + 0.02) : earliest;
      const src = ctx.createBufferSource();
      src.buffer = buf;
      src.connect(outRef.current ?? ctx.destination);
      src.playbackRate.value = cur.current.rate;
      src.start(at);
      nextAt.current = at + buf.duration / cur.current.rate;
    };

    connect();
    return () => {
      closed = true;
      clearTimeout(retry);
      ws?.close();
    };
  }, [sid, langCode]);

  return { captions, stats, session, connected, ensureAudio, analyser };
}
