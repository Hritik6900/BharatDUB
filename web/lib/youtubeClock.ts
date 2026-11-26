"use client";
import { useCallback, useEffect, useRef, type RefObject } from "react";

/**
 * Reads the time of a YouTube embed (`enablejsapi=1`) and sends it commands, over postMessage.
 * The player reports `currentTime`, `playerState` and `playbackRate` in `infoDelivery` messages once it has been
 * told someone is listening; between reports the time is carried forward while the video plays, at the speed the
 * player last reported (1 until it says otherwise).
 */
export function useYouTubeClock(iframe: RefObject<HTMLIFrameElement | null>, enabled: boolean) {
  const st = useRef({ t: 0, at: 0, state: -1, got: false, rate: 1 });

  const cmd = useCallback(
    (func: string, args: unknown[] = []) => iframe.current?.contentWindow?.postMessage(JSON.stringify({ event: "command", func, args }), "*"),
    [iframe],
  );

  useEffect(() => {
    if (!enabled) return;
    st.current = { t: 0, at: 0, state: -1, got: false, rate: 1 };
    const onMsg = (e: MessageEvent) => {
      if (!iframe.current || e.source !== iframe.current.contentWindow) return;
      let d: { info?: { currentTime?: unknown; playerState?: unknown; playbackRate?: unknown } } | null = null;
      try {
        d = typeof e.data === "string" ? JSON.parse(e.data) : e.data;
      } catch {
        return;
      }
      const info = d?.info;
      if (!info) return;
      if (typeof info.playbackRate === "number" && info.playbackRate > 0 && info.playbackRate !== st.current.rate) {
        // The speed changed: what was carried forward so far was at the old speed.
        const s = st.current;
        const t = s.got && s.state === 1 ? s.t + ((performance.now() - s.at) / 1000) * s.rate : s.t;
        st.current = { ...s, t, at: performance.now(), rate: info.playbackRate };
      }
      if (typeof info.currentTime === "number") st.current = { ...st.current, t: info.currentTime, at: performance.now(), got: true };
      if (typeof info.playerState === "number") {
        // Freeze the carried-forward time at the moment the state changes.
        const s = st.current;
        if (s.got && s.state === 1 && info.playerState !== 1 && typeof info.currentTime !== "number") {
          st.current = { ...s, t: s.t + ((performance.now() - s.at) / 1000) * s.rate, at: performance.now() };
        }
        st.current.state = info.playerState;
      }
    };
    window.addEventListener("message", onMsg);
    const hello = () => iframe.current?.contentWindow?.postMessage(JSON.stringify({ event: "listening", id: 1, channel: "widget" }), "*");
    const ping = setInterval(() => {
      if (!st.current.got) hello();
    }, 500);
    return () => {
      window.removeEventListener("message", onMsg);
      clearInterval(ping);
    };
  }, [enabled, iframe]);

  /** Seconds into the video right now, or null until the player has reported. */
  const now = useCallback((): number | null => {
    const s = st.current;
    if (!s.got) return null;
    return s.state === 1 ? s.t + ((performance.now() - s.at) / 1000) * s.rate : s.t;
  }, []);
  const playing = useCallback(() => st.current.state === 1, []);
  /** The speed the player says it plays at (1 = normal). */
  const rate = useCallback(() => st.current.rate, []);

  return { now, playing, cmd, rate };
}
