-- Bharat Dub schema (SPEC.md section 10). Run in the Supabase SQL editor or `supabase db push`.

create table if not exists voice_profiles (
  id uuid primary key default gen_random_uuid(),
  display_name text,
  sample_path text,
  embedding jsonb,
  consent_text text,
  consent_at timestamptz,
  deleted_at timestamptz,
  created_at timestamptz default now()
);

create table if not exists jobs (
  id uuid primary key default gen_random_uuid(),
  source_path text not null,
  duration_s real,
  src_lang text,
  target_langs text[] not null,
  voice_profile_id uuid references voice_profiles on delete set null,
  status text not null default 'queued',
  stage text,
  error text,
  credits_used real default 0,
  stage_timings jsonb default '{}',
  created_at timestamptz default now(),
  expires_at timestamptz
);

create table if not exists segments (
  id uuid primary key default gen_random_uuid(),
  job_id uuid references jobs on delete cascade,
  idx int not null,
  start_s real not null,
  end_s real not null,
  src_text text,
  cache_key text,
  unique (job_id, idx)
);

create table if not exists translations (
  id uuid primary key default gen_random_uuid(),
  segment_id uuid references segments on delete cascade,
  lang text not null,
  text text not null,
  edited boolean default false,
  audio_path text,
  fit_speed real,
  unique (segment_id, lang)
);

create table if not exists renders (
  id uuid primary key default gen_random_uuid(),
  job_id uuid references jobs on delete cascade,
  lang text not null,
  mp4_path text,
  srt_path text,
  created_at timestamptz default now()
);

create table if not exists glossary_terms (
  id uuid primary key default gen_random_uuid(),
  term text not null unique,
  note text
);

create table if not exists live_sessions (
  id uuid primary key default gen_random_uuid(),
  youtube_video_id text,
  src_lang text default 'indic-auto',
  target_langs text[] not null,
  voice_profile_id uuid references voice_profiles on delete set null,
  offset_ms int default 0,
  status text default 'idle',
  created_at timestamptz default now()
);

create table if not exists live_chunks (
  id bigserial primary key,
  session_id uuid references live_sessions on delete cascade,
  seq int not null,
  t_speech_ms bigint,
  src_text text,
  timings jsonb
);

create table if not exists chat_messages (
  id bigserial primary key,
  session_id uuid references live_sessions on delete cascade,
  viewer_lang text,
  text text,
  translated_text text,
  created_at timestamptz default now()
);

create index if not exists segments_job_idx on segments (job_id, idx);
create index if not exists translations_segment_idx on translations (segment_id);
create index if not exists live_chunks_session_idx on live_chunks (session_id, seq);
create index if not exists chat_session_idx on chat_messages (session_id, created_at);

-- Backend uses the service key; lock tables to everyone else.
alter table voice_profiles enable row level security;
alter table jobs enable row level security;
alter table segments enable row level security;
alter table translations enable row level security;
alter table renders enable row level security;
alter table glossary_terms enable row level security;
alter table live_sessions enable row level security;
alter table live_chunks enable row level security;
alter table chat_messages enable row level security;

-- Private storage buckets (served via signed URLs). Live audio is never stored.
insert into storage.buckets (id, name, public) values
  ('uploads', 'uploads', false),
  ('voices', 'voices', false),
  ('renders', 'renders', false)
on conflict (id) do nothing;

insert into glossary_terms (term) values
  ('bro'), ('subscribe'), ('like'), ('share'), ('reel'), ('vlog'), ('OK'), ('clutch'), ('GG')
on conflict (term) do nothing;
