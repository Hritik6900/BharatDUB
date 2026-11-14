export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000").replace(/\/$/, "");
export const WS_BASE = (process.env.NEXT_PUBLIC_WS_BASE ?? API_BASE.replace(/^http/, "ws")).replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: init?.body && !(init.body instanceof FormData) ? { "Content-Type": "application/json", ...init?.headers } : init?.headers,
    });
  } catch {
    throw new ApiError("Cannot reach the Bharat Dub server. Is the backend running?", 0);
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch {
      /* not JSON */
    }
    throw new ApiError(msg, res.status);
  }
  return res.json() as Promise<T>;
}

export interface Health {
  ok: boolean;
  configured: { gnani: boolean; llm: boolean; supabase: boolean };
  mock_providers: boolean;
}

export interface Job {
  id: string;
  source_path: string;
  duration_s: number;
  src_lang?: string;
  target_langs: string[];
  voice_profile_id?: string | null;
  status: "queued" | "running" | "done" | "failed" | "expired";
  stage?: string | null;
  error?: string | null;
  stage_timings: Record<string, unknown> & {
    _total?: number;
    _warnings?: string[];
    _usage?: Record<string, number>;
  };
  created_at?: string;
}

export interface Translation {
  id: string;
  lang: string;
  text: string;
  edited: boolean;
  fit_speed?: number | null;
}

export interface Segment {
  id: string;
  idx: number;
  start_s: number;
  end_s: number;
  src_text: string;
  translations: Translation[];
}

export interface Output {
  lang: string;
  mp4_url: string;
  srt_url: string;
  created_at?: string;
}

export interface VoiceProfile {
  id: string;
  display_name: string;
  consent_text: string;
  consent_at: string;
  created_at?: string;
}

export interface LiveSession {
  id: string;
  youtube_video_id: string | null;
  target_langs: string[];
  src_lang: string;
  offset_ms: number;
  status: "idle" | "live" | "ended";
  viewers: number;
  voice_profile_id?: string | null;
  voice_from_stream?: boolean;
  clone_langs?: string[] | null;
  /** Our GPU engine has learned the speaker's voice from this stream. */
  gpu_voice?: boolean;
  stats?: { p50_ms: number | null; p95_ms: number | null; n: number } | null;
}

export interface Dashboard {
  mock_providers: boolean;
  studio: { jobs: number; jobs_done: number; minutes_dubbed: number | null; median_turnaround_s: number | null; languages: Record<string, number> };
  live: { sessions: number; chunks: number; p50_ms: number | null; p95_ms: number | null };
  languages_supported: number;
}

export function fmtSeconds(s: number | null | undefined): string {
  if (s == null) return "";
  return s < 60 ? `${s.toFixed(1)} s` : `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`;
}
