"use client";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { Headphones, MessagesSquare, Send, SlidersHorizontal, Tag, Volume2 } from "lucide-react";
import { DelayBadge } from "@/components/ui/DelayBadge";
import { ChatList, useChat } from "@/components/live/ChatFeed";
import { Wordmark } from "@/components/layout/Logo";
import { VoiceBars } from "@/components/voice/VoiceBars";
import { VoiceOrb } from "@/components/voice/VoiceOrb";
import { useLiveFeed } from "@/lib/useLiveFeed";
import { useYouTubeClock } from "@/lib/youtubeClock";
import { useLocalNumber } from "@/lib/hooks";
import { lang } from "@/lib/langs";

const BED_VOLUME = 18; // percent: the original stream under the dub
const HOLD_MAX_S = 45; // up to this far ahead the video simply waits; beyond it, it is sent to the right place

export default function WatchPage() {
  return (
    <Suspense>
      <Watch />
    </Suspense>
  );
}

function Watch() {
  const { id } = useParams<{ id: string }>();
  const demo = useSearchParams().get("demo") === "1";
  const [choice, setChoice] = useState<string>("");
  const [listening, setListening] = useState(false);
  const [ytAudio, setYtAudio] = useState(false);
  // The stream's own sound, kept quiet under the dub: the room, the game and the laughter stay, which is what
  // makes a dub feel in step with the picture. It is the video's own audio, so it is always in sync with it.
  const [bed, setBed] = useState(false);
  const [offset, setOffset] = useLocalNumber(`bd-offset-${id}`, 0);
  const [offsetTouched, setOffsetTouched] = useState(false);
  const iframe = useRef<HTMLIFrameElement>(null);
  const subscribe = demo ? "*" : choice === "src" ? "src" : choice;
  // Sync mode: the console reports its video time; this page holds its own player `delay_ms` behind it and
  // every dubbed phrase waits for the video moment it belongs to.
  const sync = useRef<{ media: number; at: number; playing: boolean; delay: number } | null>(null);
  const [syncDelay, setSyncDelay] = useState(0);
  const hold = useRef(false); // this page paused the video so the dub can catch up
  const [hasVideo, setHasVideo] = useState(false);
  const clock = useYouTubeClock(iframe, hasVideo);
  // Where the session stands when a service behind it is away (sent once a second, only by a backend that has
  // the ladder switched on): "captions" = no voice answers for now, "original" = no dub at all for now.
  const [rung, setRung] = useState("");
  const onEvent = useCallback((m: Record<string, unknown>) => {
    if (m.type === "clock") setRung(typeof m.rung === "string" ? m.rung : "");
    if (m.type !== "sync") return;
    sync.current = { media: Number(m.media_s), at: performance.now(), playing: Boolean(m.playing), delay: Number(m.delay_ms) };
    setSyncDelay(Number(m.delay_ms));
  }, []);
  // While the video is held, it will resume from where the console's time less the delay says, so that is the
  // time phrases are scheduled against.
  const videoNow = useCallback(() => {
    const v = clock.now();
    const c = sync.current;
    // A video that is stuck (buffering, or paused by the viewer) must not hold the dub back: without a
    // running picture to match, phrases play as they arrive.
    if (v == null || !c || (!hold.current && !clock.playing())) return null;
    if (!hold.current) return v;
    return Math.min(v, c.media + (performance.now() - c.at) / 1000 - c.delay / 1000);
  }, [clock.now]); // eslint-disable-line react-hooks/exhaustive-deps
  // A streamer's own stream: the dub is timed to YouTube's delay (`offset`), not played as it arrives.
  const [mine, setMine] = useState(false);
  const feed = useLiveFeed(id, subscribe || "src", {
    audioOn: listening && choice !== "src" && !demo,
    offsetMs: mine ? 0 : offset,
    onEvent,
    videoNow,
    speechOffsetMs: mine ? offset : null,
  });
  const s = feed.session;
  useEffect(() => setHasVideo(Boolean(s?.youtube_video_id)), [s?.youtube_video_id]);
  useEffect(() => setMine(Boolean(s?.streamer_id)), [s?.streamer_id]);
  useEffect(() => {
    if (!hasVideo) return;
    let lastSeek = 0;
    const id = setInterval(() => {
      const c = sync.current;
      const age = c ? performance.now() - c.at : Infinity;
      if (!c || age > 5000) {
        if (c) {
          sync.current = null;
          setSyncDelay(0);
        }
        return;
      }
      const v = clock.now();
      if (v == null || !c.playing) return;
      // Where this player should be: the console's video time, less the delay the dub needs.
      const ahead = v - (c.media + age / 1000 - c.delay / 1000);
      // For checking sync from the browser console or a test: where the video is against where it should be.
      (window as unknown as { __bdSync?: unknown }).__bdSync = { v, ahead, hold: hold.current, delay: c.delay, playing: clock.playing() };
      if (hold.current) {
        if (ahead <= 0.15) {
          hold.current = false;
          clock.cmd("playVideo");
        }
      } else if ((ahead > HOLD_MAX_S || ahead < -3) && performance.now() - lastSeek > 3000) {
        // Far off (the streamer jumped in the video, or this player fell behind): go there.
        lastSeek = performance.now();
        clock.cmd("seekTo", [Math.max(0, v - ahead - 0.4), true]);
      } else if (ahead > 0.8 && ahead <= HOLD_MAX_S) {
        // Ahead (a viewer joins at the live edge, the stream has only just begun, or the delay grew): wait.
        // Waiting is the only thing that works on a live stream: measured 2026-11-15, a live YouTube embed
        // ignores a seek backwards but pauses and resumes fine, and resumes behind by as long as it waited.
        hold.current = true;
        clock.cmd("pauseVideo");
      } else if (!clock.playing()) clock.cmd("playVideo");
      // Within those limits nothing is touched: the dub follows this player's real time, so the delay only
      // has to be roughly right.
    }, 500);
    return () => clearInterval(id);
  }, [hasVideo, clock.now, clock.playing, clock.cmd]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (s && !choice) setChoice(s.target_langs[0] ?? "src");
    // A streamer sets how long YouTube runs behind them; a viewer who has not moved the slider follows it.
    if (s && !offsetTouched && s.offset_ms && (offset === 0 || s.streamer_id) && offset !== s.offset_ms) setOffset(s.offset_ms);
  }, [s]); // eslint-disable-line react-hooks/exhaustive-deps

  const yt = (cmd: "mute" | "unMute") =>
    iframe.current?.contentWindow?.postMessage(JSON.stringify({ event: "command", func: cmd, args: [] }), "*");
  useEffect(() => {
    // No dub for now: a viewer who is listening gets the stream's own sound until the dub is back.
    const full = ytAudio || choice === "src" || (rung === "original" && listening);
    const under = bed && listening && !full;  // only once the viewer has tapped to hear the dub
    iframe.current?.contentWindow?.postMessage(JSON.stringify({ event: "command", func: "setVolume", args: [full ? 100 : BED_VOLUME] }), "*");
    yt(full || under ? "unMute" : "mute");
  }, [ytAudio, choice, bed, listening, rung]);

  const listen = async () => {
    await feed.ensureAudio();
    setListening(true);
  };

  if (demo) return <Demo feedCaptions={feed.captions} langs={s?.target_langs ?? []} p50={feed.stats?.heard_p50_ms ?? feed.stats?.p50_ms} />;

  const caps = feed.captions.filter((c) => c.lang === (choice || "src")).slice(-2);
  const hue = choice === "src" || !choice ? "var(--hi)" : lang(choice).hue;
  const live = s?.status === "live";
  return (
    <div className="theme-dark relative min-h-dvh bg-bg text-fg">
      <div aria-hidden className="aura aura-sm" />
      <header className="relative mx-auto flex h-16 max-w-3xl items-center justify-between px-4">
        <Wordmark />
        <div className="flex items-center gap-2">
          {live && (
            <span className="inline-flex items-center gap-1.5 rounded-chip bg-danger px-2.5 py-1 text-[11px] font-semibold text-white">
              <span className="pulse-dot size-1.5 rounded-full bg-white" />
              LIVE
            </span>
          )}
          {syncDelay ? <DelayBadge ms={syncDelay} label="In step with the video, behind live by" /> : <DelayBadge ms={feed.stats?.heard_p50_ms ?? feed.stats?.p50_ms} />}
        </div>
      </header>
      <main className="relative mx-auto max-w-3xl px-4 pb-16">
        <div className="card overflow-hidden p-1.5">
          <div className="relative aspect-video overflow-hidden rounded-[18px] bg-black">
            {s?.youtube_video_id ? (
              <iframe
                ref={iframe}
                title="Live stream"
                className="absolute inset-0 size-full"
                src={`https://www.youtube-nocookie.com/embed/${s.youtube_video_id}?autoplay=1&mute=1&enablejsapi=1&playsinline=1`}
                allow="autoplay; encrypted-media; picture-in-picture"
                allowFullScreen
                onLoad={() => yt("mute")}
              />
            ) : (
              <div className="grid size-full place-items-center p-6 text-center">
                <div className="flex flex-col items-center">
                  <VoiceOrb size={104} />
                  <p className="mt-6 text-sm text-muted">{s ? "Audio and captions only for this session." : feed.connected ? "Loading…" : "Connecting to the stream…"}</p>
                </div>
              </div>
            )}
            {!listening && choice && choice !== "src" && (
              <button onClick={listen} className="absolute inset-x-3 bottom-3 inline-flex h-14 items-center justify-center gap-2.5 rounded-chip bg-fg text-lg font-medium text-on-fg">
                <Headphones aria-hidden className="size-5" />
                Tap to hear {lang(choice).name}
              </button>
            )}
          </div>

          <div className="px-4 pb-4 pt-5">
            {/* Driven by the dubbed audio that is actually playing; flat until the viewer taps to listen. */}
            <VoiceBars key={choice} analyser={feed.analyser} active={false} colors={[hue]} bars={48} height={28} />
            <p lang={choice === "src" ? "hi" : lang(choice).short} className="mt-4 min-h-[4.2em] font-indic text-[1.45rem] font-medium leading-snug" aria-live="polite">
              {caps.map((c, i) => (
                <span key={c.seq} className={i === caps.length - 1 ? "block" : "block text-base font-normal text-muted"}>
                  {c.text}
                </span>
              ))}
              {!caps.length && <span className="font-sans text-base font-normal text-muted">{live ? "Captions appear when the streamer speaks." : "The stream has not started yet."}</span>}
            </p>
            {choice !== "src" && (rung === "captions" || rung === "original") && (
              <p role="status" className="mt-3 inline-flex items-center gap-2 rounded-chip border border-line px-3 py-1 text-xs text-muted">
                <span className="pulse-dot size-1.5 rounded-full bg-fg" />
                {rung === "captions" ? "Audio returning shortly. Captions continue." : "Dub paused. You hear the original sound; the dub returns by itself."}
              </p>
            )}
            <p className="mt-2 flex items-center gap-1.5 text-xs text-muted">
              <Tag aria-hidden className="size-3.5" />
              AI-dubbed by Bharat Dub
            </p>
          </div>
        </div>

        <div role="radiogroup" aria-label="Language" className="mt-5 grid grid-cols-2 gap-2.5 sm:grid-cols-3">
          {[...(s?.target_langs ?? []), "src"].map((c) => {
            const sel = c === choice;
            const l = c === "src" ? { native: "हिन्दी", name: "Original", hue: "var(--hi)" } : lang(c);
            return (
              <button
                key={c}
                role="radio"
                aria-checked={sel}
                onClick={() => setChoice(c)}
                className={`relative flex h-[4.5rem] flex-col items-start justify-center overflow-hidden rounded-panel border px-5 text-left transition-colors ${sel ? "border-fg bg-fg text-on-fg" : "border-line bg-surface hover:border-fg/50"}`}
              >
                <span aria-hidden className="absolute right-4 top-4 size-2.5 rounded-full" style={{ background: l.hue }} />
                <span className="font-indic text-xl font-medium leading-tight">{l.native}</span>
                <span className={`text-xs ${sel ? "opacity-70" : "text-muted"}`}>{l.name}</span>
              </button>
            );
          })}
        </div>

        <div className="card mt-5 space-y-5 p-5">
          <h2 className="eyebrow flex items-center gap-2"><SlidersHorizontal aria-hidden className="size-3.5" />Sound</h2>
          {s?.youtube_video_id && (
            <label className="flex items-center justify-between gap-4">
              <span className="flex items-center gap-2.5"><Volume2 aria-hidden className="size-4 text-muted" />Original stream audio</span>
              <input type="checkbox" checked={ytAudio || choice === "src"} disabled={choice === "src"} onChange={(e) => setYtAudio(e.target.checked)} className="size-5" />
            </label>
          )}
          {s?.youtube_video_id && choice !== "src" && !ytAudio && (
            <label className="flex items-center justify-between gap-4">
              <span className="flex items-center gap-2.5"><Volume2 aria-hidden className="size-4 text-muted" />Keep the original quietly under the dub</span>
              <input type="checkbox" checked={bed} onChange={(e) => setBed(e.target.checked)} className="size-5" />
            </label>
          )}
          <label className="block">
            <span className="flex justify-between">
              <span>Sync with video</span>
              <span className="tnum font-mono text-sm text-muted">{(offset / 1000).toFixed(1)} s</span>
            </span>
            <input
              type="range"
              min={mine ? 0 : -5000}
              max={mine ? 40000 : 10000}
              step={250}
              value={offset}
              onChange={(e) => {
                setOffsetTouched(true);
                setOffset(Number(e.target.value));
              }}
              className="mt-3 w-full"
              aria-describedby="sync-hint"
            />
            <span id="sync-hint" className="mt-1 block text-xs text-muted">{mine ? "How long after the streamer speaks you hear the dub. It should match how far behind your video is: move right if the dub comes before the picture." : "If the dub runs ahead of the video, move right to delay it. Values below 0 cannot play earlier than the dub arrives."}</span>
          </label>
        </div>

        <ViewerChat sid={id} viewerLang={choice && choice !== "src" ? choice : "hi-IN"} />
      </main>
    </div>
  );
}

function ViewerChat({ sid, viewerLang }: { sid: string; viewerLang: string }) {
  const { msgs, send } = useChat(sid, viewerLang);
  const [text, setText] = useState("");
  return (
    <section className="card mt-5 p-5" aria-labelledby="chat-h">
      <h2 id="chat-h" className="eyebrow flex items-center gap-2"><MessagesSquare aria-hidden className="size-3.5" />Chat in your language</h2>
      <p className="mt-1.5 text-sm text-muted">The streamer sees it translated.</p>
      <form
        className="mt-4 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          send(text);
          setText("");
        }}
      >
        <input value={text} onChange={(e) => setText(e.target.value)} maxLength={200} lang={lang(viewerLang).short} placeholder={`Write in ${lang(viewerLang).name}…`} aria-label="Chat message" className="input min-w-0 flex-1 !rounded-chip" />
        <button aria-label="Send" className="grid size-12 shrink-0 place-items-center rounded-full bg-fg text-on-fg disabled:opacity-40" disabled={!text.trim()}>
          <Send aria-hidden className="size-[18px]" />
        </button>
      </form>
      <div className="mt-4 max-h-64 overflow-y-auto"><ChatList msgs={msgs} /></div>
    </section>
  );
}

function Demo({ feedCaptions, langs, p50 }: { feedCaptions: { seq: number; lang: string; text: string }[]; langs: string[]; p50: number | null | undefined }) {
  const cols = ["src", ...langs];
  return (
    <div className="theme-dark relative min-h-dvh bg-bg p-6 text-fg sm:p-10">
      <div aria-hidden className="aura aura-sm" />
      <div className="relative flex items-center justify-between">
        <Wordmark />
        <DelayBadge ms={p50} large />
      </div>
      <div className="relative mt-10 grid gap-5" style={{ gridTemplateColumns: `repeat(${Math.min(cols.length, 4)}, minmax(0,1fr))` }}>
        {cols.map((c) => {
          const l = c === "src" ? { name: "Original (Hindi)", hue: "var(--hi)", short: "hi" } : lang(c);
          const caps = feedCaptions.filter((x) => x.lang === c).slice(-3);
          return (
            <section key={c} className="card relative overflow-hidden p-6 sm:p-7">
              <span aria-hidden className="absolute inset-x-0 top-0 h-1" style={{ background: l.hue }} />
              <h2 className="flex items-center gap-3 text-xl font-medium"><span className="size-3 rounded-full" style={{ background: l.hue }} />{l.name}</h2>
              <ul className="mt-6 space-y-4 font-indic" lang={l.short}>
                {caps.map((x, i) => (
                  <li key={x.seq} className={i === caps.length - 1 ? "text-[1.9rem] font-medium leading-snug" : "text-lg text-muted"}>{x.text}</li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>
      <p className="relative mt-8 flex items-center gap-2 text-sm text-muted"><Tag aria-hidden className="size-4" />AI-dubbed by Bharat Dub</p>
    </div>
  );
}
