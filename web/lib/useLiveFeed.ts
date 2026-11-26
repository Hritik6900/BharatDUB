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
  /** End of a phrase to the moment a viewer starts hearing its dub (after earlier phrases have played). */
  heard_p50_ms?: number | null;
  heard_p95_ms?: number | null;
  /** Sync mode: how far behind viewers hold the video, and the share of phrases that started on their moment. */
  sync_delay_ms?: number;
  sync_on_time_pct?: number;
  sync_late_p95_ms?: number;
  /** Measured by viewers' players: phrases that started within 1 s of their moment, and how many reported. */
  viewer_n?: number;
  viewer_on_time_pct?: number;
  viewer_late_p95_ms?: number;
}

const JITTER_S = 0.3;
// Dubbed speech can run longer than the original. When more than CATCHUP_AFTER_S of audio is waiting, play a little
// faster; a chunk that would start more than MAX_BACKLOG_S late is skipped (its caption still shows).
const CATCHUP_AFTER_S = 2;
const CATCHUP_RATE = 1.1;
const MAX_BACKLOG_S = 10;
// Sync mode: a phrase carries the video time it was spoken at (`media_s`) and is held until the viewer's own
// player reaches it. Anything further away than this is treated as a clock mix-up and played as it arrives.
const MAX_SYNC_WAIT_S = 20;

/**
 * Subscribes to /ws/watch/{sid}?lang=. Captions always; audio is decoded and scheduled back-to-back
 * with a 300 ms jitter buffer plus `offsetMs` (sync with the YouTube player) when `audioOn`.
 */
export function useLiveFeed(
  sid: string,
  langCode: string,
  opts: {
    audioOn: boolean;
    offsetMs: number;
    onEvent?: (m: Record<string, unknown>) => void;
    videoNow?: () => number | null;
    /** The speed the viewer's video plays at (1 = normal): a phrase due in 2 s of video is due sooner at 1.1x. */
    videoRate?: () => number;
    /** A streamer's own mic: every phrase plays this long after it was spoken (YouTube's delay). null = off. */
    speechOffsetMs?: number | null;
  },
) {
  const [captions, setCaptions] = useState<Caption[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [session, setSession] = useState<LiveSession | null>(null);
  const [connected, setConnected] = useState(false);
  const ctxRef = useRef<AudioContext | null>(null);
  const nextAt = useRef(0);
  const cur = useRef({ seq: -1, drop: false, rate: 1 });
  const lastSync = useRef(0); // when the console last reported its video time
  // Session clock -> this page's clock: the smallest (arrival - sent) seen is the truest, the rest is network delay.
  const clockOff = useRef<number | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
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
      wsRef.current = ws;
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
        else if (m.type === "sync") lastSync.current = performance.now();
        else if (m.type === "clock") {
          const off = performance.now() - Number(m.t_ms);
          clockOff.current = clockOff.current == null ? off : Math.min(clockOff.current + 0.5, off);
        }
        else if (m.type === "caption") {
          const wait = m.history ? null : untilVideo(m.media_s) ?? untilSpoken(m.t_speech_ms);
          const delay = m.history ? 0 : wait != null ? Math.max(0, wait * 1000) : Math.max(0, optsRef.current.offsetMs);
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
          schedule(m.pcm_b64, m.sample_rate, m.seq, m.media_s, m.t_speech_ms);
        }
      };
    };

    /** Seconds until the viewer's video reaches `mediaS` (plus the sync slider), or null when not in sync mode. */
    const untilVideo = (mediaS: unknown): number | null => {
      if (typeof mediaS !== "number" || performance.now() - lastSync.current > 5000) return null;
      const v = optsRef.current.videoNow?.();
      if (v == null) return null;
      const speed = optsRef.current.videoRate?.() || 1;
      const wait = (mediaS - v) / speed + optsRef.current.offsetMs / 1000;
      return wait > MAX_SYNC_WAIT_S ? null : wait;
    };

    /** Seconds until a phrase spoken at session time `tSpeech` is due (its moment + the offset), or null. */
    const untilSpoken = (tSpeech: unknown): number | null => {
      const off = optsRef.current.speechOffsetMs;
      if (off == null || clockOff.current == null || typeof tSpeech !== "number") return null;
      return (tSpeech + off + clockOff.current - performance.now()) / 1000;
    };

    const schedule = (b64: string, rate: number, seq: number, mediaS?: number, tSpeech?: number) => {
      const ctx = ctxRef.current;
      if (!ctx || ctx.state !== "running") return;
      let due: number | null = null;
      if (seq !== cur.current.seq) {
        // Decide once per chunk, so a sentence is never cut or sped up halfway.
        const backlog = Math.max(0, nextAt.current - ctx.currentTime);
        const wait = untilVideo(mediaS) ?? untilSpoken(tSpeech);
        if (wait != null) {
          // Tell the server how late this phrase really starts here (0 = on its moment): measured, not estimated.
          const queuedFor = Math.max(0, nextAt.current - ctx.currentTime);
          const lateMs = Math.round(Math.max(0, Math.max(queuedFor, 0.05) - wait) * 1000);
          if (wsRef.current?.readyState === WebSocket.OPEN) wsRef.current.send(JSON.stringify({ type: "played", seq, late_ms: lateMs }));
          // In step with the video: the server already fits each phrase to its moment, so no catch-up here.
          due = ctx.currentTime + wait;
          // For checking sync: how long before (or, negative, after) its video moment each phrase arrived.
          const w = window as unknown as { __bdDue?: { seq: number; wait: number }[] };
          (w.__bdDue ??= []).push({ seq, wait: Math.round(wait * 1000) });
          if (w.__bdDue.length > 200) w.__bdDue.shift();
          cur.current = { seq, drop: false, rate: 1 };
        } else cur.current = { seq, drop: backlog > MAX_BACKLOG_S, rate: backlog > CATCHUP_AFTER_S ? CATCHUP_RATE : 1 };
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
      const queued = nextAt.current > ctx.currentTime ? Math.max(nextAt.current, ctx.currentTime + 0.02) : null;
      const at = due != null ? Math.max(due, queued ?? ctx.currentTime + 0.05) : queued ?? earliest;
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
