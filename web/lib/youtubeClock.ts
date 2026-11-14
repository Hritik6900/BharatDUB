"use client";
import { useCallback, useEffect, useRef, type RefObject } from "react";

/**
 * Reads the time of a YouTube embed (`enablejsapi=1`) and sends it commands, over postMessage.
 * The player reports `currentTime` and `playerState` in `infoDelivery` messages once it has been told
 * someone is listening; between reports the time is carried forward while the video plays.
 */
export function useYouTubeClock(iframe: RefObject<HTMLIFrameElement | null>, enabled: boolean) {
  const st = useRef({ t: 0, at: 0, state: -1, got: false });

  const cmd = useCallback(
    (func: string, args: unknown[] = []) => iframe.current?.contentWindow?.postMessage(JSON.stringify({ event: "command", func, args }), "*"),
    [iframe],
  );

  useEffect(() => {
    if (!enabled) return;
    st.current = { t: 0, at: 0, state: -1, got: false };
    const onMsg = (e: MessageEvent) => {
      if (!iframe.current || e.source !== iframe.current.contentWindow) return;
      let d: { info?: { currentTime?: unknown; playerState?: unknown } } | null = null;
      try {
        d = typeof e.data === "string" ? JSON.parse(e.data) : e.data;
      } catch {
        return;
      }
      const info = d?.info;
      if (!info) return;
      if (typeof info.currentTime === "number") st.current = { ...st.current, t: info.currentTime, at: performance.now(), got: true };
      if (typeof info.playerState === "number") {
        // Freeze the carried-forward time at the moment the state changes.
        const s = st.current;
        if (s.got && s.state === 1 && info.playerState !== 1 && typeof info.currentTime !== "number") {
          st.current = { ...s, t: s.t + (performance.now() - s.at) / 1000, at: performance.now() };
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
    return s.state === 1 ? s.t + (performance.now() - s.at) / 1000 : s.t;
  }, []);
  const playing = useCallback(() => st.current.state === 1, []);

  return { now, playing, cmd };
}
