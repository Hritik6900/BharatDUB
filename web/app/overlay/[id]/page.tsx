"use client";
import { useParams } from "next/navigation";
import { useChat } from "@/components/live/ChatFeed";
import { lang } from "@/lib/langs";

/** OBS browser source: translated viewer chat on a transparent background. */
export default function Overlay() {
  const { id } = useParams<{ id: string }>();
  const { msgs } = useChat(id, "hi-IN");
  return (
    <>
      <style>{"html,body{background:transparent!important}"}</style>
      <ul className="fixed inset-x-4 bottom-4 space-y-2">
        {msgs.slice(-6).map((m) => (
          <li key={m.id} className="rise w-fit max-w-[90vw] rounded-[18px] border border-white/10 bg-[#0b0a0f]/85 px-5 py-3 text-[1.5rem] leading-snug text-white backdrop-blur">
            <span className="mr-2.5 inline-block size-3 rounded-full align-middle" style={{ background: lang(m.viewer_lang).hue }} />
            {m.name && <span className="mr-2 font-semibold">{m.name}</span>}
            <span lang="hi" className="font-indic">{m.translated}</span>
          </li>
        ))}
      </ul>
    </>
  );
}
