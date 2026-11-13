"use client";
import { useCallback, useEffect, useRef, useState } from "react";

export type MicState = "off" | "asking" | "on" | "error";

/** Local microphone -> AnalyserNode, for visuals only. Nothing is recorded or sent anywhere. */
export function useMic() {
  const [state, setState] = useState<MicState>("off");
  const [analyser, setAnalyser] = useState<AnalyserNode | null>(null);
  const [error, setError] = useState("");
  const res = useRef<{ ctx: AudioContext; stream: MediaStream } | null>(null);

  const stop = useCallback(() => {
    res.current?.stream.getTracks().forEach((t) => t.stop());
    void res.current?.ctx.close();
    res.current = null;
    setAnalyser(null);
    setState("off");
  }, []);

  const start = useCallback(async () => {
    setState("asking");
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const ctx = new AudioContext();
      const an = ctx.createAnalyser();
      an.fftSize = 1024;
      an.smoothingTimeConstant = 0.8;
      ctx.createMediaStreamSource(stream).connect(an);
      res.current = { ctx, stream };
      setAnalyser(an);
      setState("on");
    } catch (e) {
      setError((e as Error).message);
      setState("error");
    }
  }, []);

  useEffect(() => stop, [stop]);
  return { state, analyser, error, start, stop };
}

/** An AnalyserNode tapped off an existing audio node (mic source, media element). */
export function useAnalyser(node: AudioNode | null, ctx: AudioContext | null): AnalyserNode | null {
  const [an, setAn] = useState<AnalyserNode | null>(null);
  useEffect(() => {
    if (!node || !ctx) {
      setAn(null);
      return;
    }
    const a = ctx.createAnalyser();
    a.fftSize = 1024;
    a.smoothingTimeConstant = 0.8;
    node.connect(a);
    setAn(a);
    return () => {
      try {
        node.disconnect(a);
      } catch {
        /* already gone */
      }
    };
  }, [node, ctx]);
  return an;
}
