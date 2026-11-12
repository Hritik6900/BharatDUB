"use client";
import { useEffect, useRef, useState } from "react";
import { WS_BASE } from "@/lib/api";
import { lang } from "@/lib/langs";

export interface ChatMsg {
  id: number | string;
  viewer_lang: string;
  name?: string;
  text: string;
  translated: string;
  at: string;
}

/** Chat socket: receives translated messages; `send` posts one (1 per second, server-side limit). */
export function useChat(sid: string, viewerLang: string) {
  const [msgs, setMsgs] = useState<ChatMsg[]>([]);
  const ws = useRef<WebSocket | null>(null);
  useEffect(() => {
    if (!sid) return;
    let closed = false;
    let retry: ReturnType<typeof setTimeout>;
    const connect = () => {
      const s = new WebSocket(`${WS_BASE}/ws/chat/${sid}?lang=${viewerLang}`);
      s.onmessage = (e) => {
        const m = JSON.parse(e.data);
        if (m.type === "chat") setMsgs((x) => [...x.filter((y) => y.id !== m.id), m].slice(-60));
      };
      s.onclose = () => !closed && (retry = setTimeout(connect, 2000));
      ws.current = s;
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(retry);
      ws.current?.close();
    };
  }, [sid, viewerLang]);
  const send = (text: string, name = "") => {
    if (ws.current?.readyState === WebSocket.OPEN && text.trim()) ws.current.send(JSON.stringify({ text, lang: viewerLang, name }));
  };
  return { msgs, send };
}

export function ChatList({ msgs, showOriginal = true, large = false }: { msgs: ChatMsg[]; showOriginal?: boolean; large?: boolean }) {
  const end = useRef<HTMLLIElement>(null);
  useEffect(() => {
    // Newer browsers return a Promise from scrollIntoView; never return it from an effect.
    end.current?.scrollIntoView({ block: "nearest" });
  }, [msgs.length]);
  if (!msgs.length) return <p className="text-sm text-slate">No messages yet.</p>;
  return (
    <ul className={`space-y-3 ${large ? "text-2xl" : ""}`}>
      {msgs.map((m) => (
        <li key={m.id}>
          <p>
            {m.name && <span className="mr-2 font-display font-semibold">{m.name}</span>}
            <span lang="hi">{m.translated}</span>
          </p>
          {showOriginal && m.translated !== m.text && (
            <p className="text-sm text-slate">
              <span className="mr-1.5 inline-block size-2 rounded-full align-middle" style={{ background: lang(m.viewer_lang).hue }} />
              {lang(m.viewer_lang).name}: {m.text}
            </p>
          )}
        </li>
      ))}
      <li ref={end} aria-hidden />
    </ul>
  );
}
