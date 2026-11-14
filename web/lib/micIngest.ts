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
  /** A JSON note on the ingest socket (the console reports the video time this way). */
  send: (msg: Record<string, unknown>) => void;
}

/** `player`: the YouTube video embedded in the console itself (this tab), which also gives its time for sync. */
export type IngestSource = "mic" | "tab" | "player";

/** Sound of a browser tab (or the whole PC), untouched: the mic's echo canceller removes speaker sound, so a
 *  stream playing on this computer has to be captured this way. The video track is not needed and is dropped. */
async function tabAudio(self = false): Promise<MediaStream> {
  const s = await navigator.mediaDevices.getDisplayMedia({
    video: { displaySurface: "browser" },
    monitorTypeSurfaces: "exclude",
    systemAudio: "exclude",
    // `self`: capture this very tab (the console never plays the dub, so nothing loops).
    selfBrowserSurface: self ? "include" : "exclude",
    preferCurrentTab: self,
    // suppressLocalAudioPlayback: the shared tab goes silent on the speakers but is still captured,
    // so the streamer hears only the dub (Chromium; ignored elsewhere).
    audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, suppressLocalAudioPlayback: true } as MediaTrackConstraints,
  } as DisplayMediaStreamOptions);
  if (s.getVideoTracks()[0]?.getSettings().displaySurface !== "browser") {
    s.getTracks().forEach((t) => t.stop());
    throw new Error("Pick a browser tab, not a window or the whole screen. Those carry every sound on this PC, so the dub would be heard and dubbed again.");
  }
  if (!s.getAudioTracks().length) {
    s.getTracks().forEach((t) => t.stop());
    throw new Error("No sound was shared. Pick a tab and tick \"Also share tab audio\".");
  }
  // The picture is not used, but the video track stays open: ending it can end the capture session's
  // local mute. It is turned down to almost nothing instead.
  s.getVideoTracks().forEach((t) => void t.applyConstraints({ frameRate: 1, width: 160 }).catch(() => {}));
  return s;
}

export async function startMicIngest(
  sid: string,
  token: string,
  onStatus: (s: "connecting" | "live" | "closed" | "error", detail?: string) => void,
  from: IngestSource = "mic",
): Promise<MicIngest> {
  onStatus("connecting");
  const stream = from !== "mic" ? await tabAudio(from === "player") : await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  });
  stream.getAudioTracks()[0]?.addEventListener("ended", () => onStatus("closed", from !== "mic" ? "Sharing stopped." : undefined));
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
    send: (msg) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
    },
    stop: () => {
      tap.port.onmessage = null;
      ws.close();
      stream.getTracks().forEach((t) => t.stop());
      void ctx.close();
    },
  };
}
