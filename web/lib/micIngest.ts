"use client";
/** Browser mic -> 16 kHz mono PCM16 -> /ws/ingest/{sid}?token=. Same wire format as ingest_client/client.py. */
import { WS_BASE } from "./api";

const WORKLET = `
class Tap extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch) this.port.postMessage(ch.slice(0));
    return true;
  }
}
registerProcessor("bd-tap", Tap);
`;

export interface MicIngest {
  stop: () => void;
  ctx: AudioContext;
  source: MediaStreamAudioSourceNode;
}

export async function startMicIngest(
  sid: string,
  token: string,
  onStatus: (s: "connecting" | "live" | "closed" | "error", detail?: string) => void,
): Promise<MicIngest> {
  onStatus("connecting");
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  });
  const ctx = new AudioContext({ sampleRate: 16000 }); // browser resamples the mic for us
  const url = URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" }));
  await ctx.audioWorklet.addModule(url);
  URL.revokeObjectURL(url);
  const source = ctx.createMediaStreamSource(stream);
  const tap = new AudioWorkletNode(ctx, "bd-tap");
  source.connect(tap);

  const ws = new WebSocket(`${WS_BASE}/ws/ingest/${sid}?token=${encodeURIComponent(token)}`);
  ws.binaryType = "arraybuffer";
  let buf = new Int16Array(0);
  ws.onopen = () => onStatus("live");
  ws.onclose = (e) => onStatus(e.code === 4403 ? "error" : "closed", e.code === 4403 ? "Ingest token was refused." : undefined);
  ws.onerror = () => onStatus("error", "Could not connect to the backend.");

  tap.port.onmessage = (e: MessageEvent<Float32Array>) => {
    if (ws.readyState !== WebSocket.OPEN) return;
    const f = e.data;
    const pcm = new Int16Array(f.length);
    for (let i = 0; i < f.length; i++) pcm[i] = Math.max(-1, Math.min(1, f[i])) * 0x7fff;
    const merged = new Int16Array(buf.length + pcm.length);
    merged.set(buf);
    merged.set(pcm, buf.length);
    let off = 0;
    while (merged.length - off >= 512) {
      ws.send(merged.slice(off, off + 512).buffer); // 1024 bytes = 32 ms
      off += 512;
    }
    buf = merged.slice(off);
  };

  return {
    ctx,
    source,
    stop: () => {
      tap.port.onmessage = null;
      ws.close();
      stream.getTracks().forEach((t) => t.stop());
      void ctx.close();
    },
  };
}
