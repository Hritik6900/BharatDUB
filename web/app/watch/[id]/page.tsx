"use client";
import { Suspense, useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { DelayBadge } from "@/components/ui/DelayBadge";
import { ChatList, useChat } from "@/components/live/ChatFeed";
import { useLiveFeed } from "@/lib/useLiveFeed";
import { useLocalNumber } from "@/lib/hooks";
import { lang } from "@/lib/langs";
import { Wordmark } from "@/components/layout/Nav";

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
  const [offset, setOffset] = useLocalNumber(`bd-offset-${id}`, 0);
  const [offsetTouched, setOffsetTouched] = useState(false);
  const iframe = useRef<HTMLIFrameElement>(null);
  const subscribe = demo ? "*" : choice === "src" ? "src" : choice;
  const feed = useLiveFeed(id, subscribe || "src", { audioOn: listening && choice !== "src" && !demo, offsetMs: offset });
  const s = feed.session;

  useEffect(() => {
    if (s && !choice) setChoice(s.target_langs[0] ?? "src");
    if (s && !offsetTouched && s.offset_ms && offset === 0) setOffset(s.offset_ms);
  }, [s]); // eslint-disable-line react-hooks/exhaustive-deps

  const yt = (cmd: "mute" | "unMute") =>
    iframe.current?.contentWindow?.postMessage(JSON.stringify({ event: "command", func: cmd, args: [] }), "*");
  useEffect(() => {
    yt(ytAudio || choice === "src" ? "unMute" : "mute");
  }, [ytAudio, choice]);

  const listen = async () => {
    await feed.ensureAudio();
    setListening(true);
  };

  if (demo) return <Demo feedCaptions={feed.captions} langs={s?.target_langs ?? []} p50={feed.stats?.p50_ms} />;

  const caps = feed.captions.filter((c) => c.lang === (choice || "src")).slice(-2);
  const hue = choice === "src" || !choice ? "var(--hi)" : lang(choice).hue;
  return (
    <div className="theme-dark min-h-dvh bg-bg text-fg">
      <header className="mx-auto flex h-14 max-w-3xl items-center justify-between px-4">
        <Wordmark />
        <DelayBadge ms={feed.stats?.p50_ms} />
      </header>
      <main className="mx-auto max-w-3xl px-4 pb-16">
        <div className="relative aspect-video overflow-hidden rounded-media bg-black">
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
            <div className="grid size-full place-items-center p-6 text-center text-slate">
              {s ? "Audio and captions only for this session." : feed.connected ? "Loading…" : "Connecting to the stream…"}
            </div>
          )}
          {!listening && choice && choice !== "src" && (
            <button onClick={listen} className="absolute inset-x-0 bottom-0 m-3 h-14 rounded-chip bg-fg font-display text-lg font-semibold text-on-fg">
              Tap to hear {lang(choice).name}
            </button>
          )}
        </div>

        <p lang={choice === "src" ? "hi" : lang(choice).short} className="mt-5 min-h-[4.2em] font-display text-[1.45rem] leading-snug" aria-live="polite">
          {caps.map((c, i) => (
            <span key={c.seq} className={i === caps.length - 1 ? "" : "block text-base text-slate"}>
              {i === caps.length - 1 ? <span className="border-b-2 pb-0.5" style={{ borderColor: hue }}>{c.text}</span> : c.text}
            </span>
          ))}
          {!caps.length && <span className="text-base text-slate">{s?.status === "live" ? "Captions appear when the streamer speaks." : "The stream has not started yet."}</span>}
        </p>
        <p className="mt-1 text-xs text-slate">AI-dubbed by Bharat Dub</p>

        <div role="radiogroup" aria-label="Language" className="mt-6 grid grid-cols-2 gap-2.5 sm:grid-cols-3">
          {[...(s?.target_langs ?? []), "src"].map((c) => {
            const sel = c === choice;
            const l = c === "src" ? { native: "हिन्दी", name: "Original", hue: "var(--hi)" } : lang(c);
            return (
              <button
                key={c}
                role="radio"
                aria-checked={sel}
                onClick={() => setChoice(c)}
                style={{ ["--hue" as string]: l.hue }}
                className={`flex h-16 flex-col items-start justify-center rounded-panel border px-4 text-left font-display ${sel ? "border-[var(--hue)] bg-[var(--hue)] text-white" : "border-mist bg-surface"}`}
              >
                <span className="text-lg leading-tight">{l.native}</span>
                <span className={`text-xs ${sel ? "text-white/85" : "text-slate"}`}>{l.name}</span>
              </button>
            );
          })}
        </div>

        <div className="mt-8 space-y-5 rounded-panel border border-mist p-4">
          {s?.youtube_video_id && (
            <label className="flex items-center justify-between gap-4">
              <span>Original stream audio</span>
              <input type="checkbox" checked={ytAudio || choice === "src"} disabled={choice === "src"} onChange={(e) => setYtAudio(e.target.checked)} className="size-5" />
            </label>
          )}
          <label className="block">
            <span className="flex justify-between">
              <span>Sync with video</span>
              <span className="tnum text-slate">{(offset / 1000).toFixed(1)} s</span>
            </span>
            <input
              type="range"
              min={-5000}
              max={10000}
              step={250}
              value={offset}
              onChange={(e) => {
                setOffsetTouched(true);
                setOffset(Number(e.target.value));
              }}
              className="mt-2 w-full"
              aria-describedby="sync-hint"
            />
            <span id="sync-hint" className="text-xs text-slate">If the dub runs ahead of the video, move right to delay it. Values below 0 cannot play earlier than the dub arrives.</span>
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
    <section className="mt-8" aria-labelledby="chat-h">
      <h2 id="chat-h" className="font-display text-lg font-semibold">Chat in your language</h2>
      <p className="text-sm text-slate">The streamer sees it translated.</p>
      <form
        className="mt-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          send(text);
          setText("");
        }}
      >
        <input value={text} onChange={(e) => setText(e.target.value)} maxLength={200} lang={lang(viewerLang).short} placeholder={`Write in ${lang(viewerLang).name}…`} aria-label="Chat message" className="h-12 min-w-0 flex-1 rounded-chip border border-mist bg-surface px-4" />
        <button className="h-12 rounded-chip bg-fg px-5 font-display text-on-fg" disabled={!text.trim()}>Send</button>
      </form>
      <div className="mt-4 max-h-64 overflow-y-auto"><ChatList msgs={msgs} /></div>
    </section>
  );
}

function Demo({ feedCaptions, langs, p50 }: { feedCaptions: { seq: number; lang: string; text: string }[]; langs: string[]; p50: number | null | undefined }) {
  const cols = ["src", ...langs];
  return (
    <div className="theme-dark min-h-dvh bg-bg p-6 text-fg sm:p-10">
      <div className="flex items-center justify-between">
        <Wordmark />
        <DelayBadge ms={p50} large />
      </div>
      <div className="mt-10 grid gap-6" style={{ gridTemplateColumns: `repeat(${Math.min(cols.length, 4)}, minmax(0,1fr))` }}>
        {cols.map((c) => {
          const l = c === "src" ? { name: "Original (Hindi)", hue: "var(--hi)", short: "hi" } : lang(c);
          const caps = feedCaptions.filter((x) => x.lang === c).slice(-3);
          return (
            <section key={c} className="rounded-media border border-mist p-6">
              <h2 className="flex items-center gap-3 font-display text-2xl font-semibold"><span className="size-3 rounded-full" style={{ background: l.hue }} />{l.name}</h2>
              <ul className="mt-6 space-y-4 font-display" lang={l.short}>
                {caps.map((x, i) => (
                  <li key={x.seq} className={i === caps.length - 1 ? "text-[1.9rem] leading-snug" : "text-lg text-slate"}>{x.text}</li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>
      <p className="mt-8 text-sm text-slate">AI-dubbed by Bharat Dub</p>
    </div>
  );
}
