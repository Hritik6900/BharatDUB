-- Live can learn the speaker's voice from the stream; holds {consent_at, consent_text} given at session creation.
alter table live_sessions add column if not exists voice_from_stream jsonb;
