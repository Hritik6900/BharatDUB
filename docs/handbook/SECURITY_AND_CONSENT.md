# Security and consent

What Bharat Dub asks before it copies a voice, what it keeps and for how long, what it logs, how secrets are
handled, which licences need watching, and the gaps. Dated 2026-11-25.
Sources: SPEC sections 2, 15, 16 and 20; `STREAMER_MODE.md`; `backend/app/live/routes.py`, `backend/app/config.py`,
`backend/app/main.py` (read for this page); `logs/README.md`; `docs/v1/MODELS.md`; `docs/v1/RUNBOOK.md`.

## 1. Consent gates cloning

Rule (SPEC section 2, rule 4): no call that copies a voice unless the voice profile has `consent_at` set. No
exceptions, no debug bypass. The backend refuses with HTTP 403 otherwise (SPEC section 15).

| Where a voice comes from | How consent is taken | Since | Source |
|---|---|---|---|
| `/voices` profile | sample + `consent_text` + `consent=true` on `POST /api/voices` | 13 Nov 2026 | SPEC section 11 |
| **Streamer Mode** recording | the consent sentence is **read aloud** in the recording; no consent, no profile (403) | 15 Nov 2026 | `STREAMER_MODE.md` section A |
| **Voice learned from the stream** on `/live` | a consent tick on the console (`voice_from_stream=true` + `voice_consent=true`); the sentence starts "The voice on this stream is mine, or I have the speaker's permission ..." | 13 Nov 2026 | SPEC section 16; `live/routes.py` |
| **Voice from the uploaded video** (Studio) | a checkbox at upload (`voice_from_video=true` + `voice_consent=true`), not read aloud | 13 Nov 2026 | SPEC section 16 |
| Studio upload itself | "I own this video or have permission" is required | 13 Nov 2026 | SPEC section 15 |

- `live_clone_needs_streamer`: **off since 15 Nov 2026, by the founder's choice** (`10bd8e1` / `89b68e4`). Off, `/live`
  may copy the voice on the stream behind its consent tick. On, only a streamer profile (consent read aloud) may
  clone and the `/live` form is stock only. Default in `backend/app/config.py`: `False`.
- v1 flag `V1_LIVE_STOCK_DEFAULT` (recommended on): a `/live` session without a streamer profile speaks in stock
  voices even with the tick set.
- A profile made from a stream or a video is a normal profile with `consent_at` ("Voice from live <time>",
  "Voice from <file>"), reusable and deletable on `/voices`.
- v0's consent records are not copied into v1: voices are recorded again in v1 with consent
  (`scripts/v1/copy-voice-samples.sh`, `docs/v1/DISCOVERY.md` risk 5).
- Every output is labelled "AI-dubbed by Bharat Dub" (SRT first cue + UI label).
- No dubbing of third-party broadcasts (sports, news) in this version.

Decided in [ADR-0005](adr/0005-consent-gates-cloning.md), [ADR-0012](adr/0012-streamer-mode-recorded-voice.md).

## 2. Data handling and retention

| Data | Kept where | How long | Source |
|---|---|---|---|
| Uploaded videos and job files | `<DATA_DIR>/jobs/<id>/` (or the `uploads` bucket with Supabase) | deleted after `UPLOAD_TTL_HOURS` (24 h) by the backend's cleanup of local job files past `expires_at` | SPEC section 15; `backend/app/main.py` |
| Renders (MP4, SRT) | local disk, or the `renders` bucket | not stated (unconfirmed) | SPEC section 18 |
| Voice samples and engine cuts | `<DATA_DIR>/voices/`; profiles in the store | until deleted: one click on `/voices` (`DELETE /api/voices/{id}`) | SPEC section 15 |
| Voices held by the GPU engines | in the engine processes | until the engine is restarted (82 voices on one engine on 23 Nov) | `docs/v1/DISCOVERY.md` risk 9 |
| Live audio | **never stored** | - | SPEC section 10 |
| Live dub, opt-in exception | `<DATA_DIR>/recordings/<session>/` only with `V1_LIVE_RECORD=true` **and** `record: true` on that session (a tick that says what is kept) | deleted by itself `V1_RECORD_KEEP_DAYS` (30) days after it ended (checked at backend start and every half hour); any one deletable at once (`/live`, `DELETE /api/v1/recordings/<session>`); deleting a voice does not delete recordings in it | [ADR-0034](adr/0034-recording-retention.md); `../v1/RUNBOOK.md` section 3; NEEDS_APPROVAL item 25 |
| Studio HQ review edits (words) | `<DATA_DIR>/hq_review/<job>.jsonl` | not stated (unconfirmed) | `../v1/RUNBOOK.md` |
| Cache (transcripts, translations, voice lines) | `<DATA_DIR>/cache/<stage>/` | not stated (unconfirmed) | SPEC section 18 |

- v1's data folder is `data-v1\` in the v1 folder; it is git-ignored and never committed. v0's is `backend\data`
  in the v0 folder. v1 never reads or writes v0's data.
- Retention for recordings, review edits and cache is an open decision ([OPEN_QUESTIONS.md](OPEN_QUESTIONS.md)).

Decided in [ADR-0004](adr/0004-local-json-store.md), [ADR-0032](adr/0032-opt-in-live-recording.md).

## 3. What is logged, and what never is

`logs/README.md`: the `logs/` folder holds **measurements only**.

| Logged | Never logged |
|---|---|
| per outbound request: call, host, path, status, ms, attempt, bytes (`V1_API_LOG`) | request or response bodies |
| per Live phrase: ms per step, how late, tempo, copied or stock, GPU or hosted, skipped and why, lengths in words and letters | source text, translation, captions |
| per Studio line: who judged it, score, takes, flagged; review edit sizes and the failed rule | the words of a line or an edit |
| stream watcher events and 20 s rows | audio, voice samples |
| session and job ids (first 8 characters) | keys, voice or token ids |

The caption text of a recorded session is in its recording folder only, not in the trace and not in `logs/`.
YouTube video ids appear in `logs/sessions/index.csv`; handbook pages do not list them.

Decided in [ADR-0022](adr/0022-trace-and-logs.md).

## 4. Secrets

- Keys only from env (`backend/.env`, `web/.env.local`); never hardcoded, never logged, never sent to the browser
  (SPEC section 2, rule 6). Key names: `backend/.env.example` (no values).
- `.env`, `.env.local`, `*.env`, `.env.v1` are git-ignored; only `*.env.example` is tracked.
- The SSH key file and the VM's address appear only in `docs/v1/NEEDS_APPROVAL.md`. Do not copy them elsewhere.
- Hugging Face tokens for gated models are typed on the VM at start and never written to a file in the repository
  (NEEDS_APPROVAL items 7 and 11).
- Moving the backend to the VM copies `backend/.env` with `scp` and never shows it (NEEDS_APPROVAL item 2).
- The `pre-commit` hook refuses assistant mentions, zips and files over 10 MB. It does **not** scan for keys: the
  git-ignore rules and review are the only guard against a key in a commit.

Decided in [ADR-0023](adr/0023-repo-hygiene.md).

## 5. Licences to watch

Details per model: [MODELS.md](MODELS.md), [`../v1/MODELS.md`](../v1/MODELS.md).

| Model | Issue | State |
|---|---|---|
| ECAPA2 | CC-BY-NC-4.0: non-commercial | rejected; QA server refuses it unless `QA_SPK_ALLOW_NONCOMMERCIAL=1` for a measurement that ships nothing ([ADR-0025](adr/0025-speaker-model-licence.md)) |
| speechbrain ECAPA-TDNN | Apache-2.0; trained on VoxCeleb, whose page states no licence | in use for QA; legal question listed for the founder |
| Indic Transcribe | self-hosting yes; a hosted service others call needs the authors' written sign-off; separate licence above 500 M monthly users or 250 M dollars revenue | gated on the founder's decision ([ADR-0026](adr/0026-gated-models.md)) |
| pyannote community-1 | CC-BY-4.0, attribution; terms share contact details | gated on accepting terms |
| IndicF5 | MIT tag on its card, gated; terms: copy only voices you have permission for. A model fine-tuned from it (`dheeyantra/dhee-indic-f5`) says its lineage is non-commercial (F5-TTS trained on Emilia, CC-BY-NC-4.0; IIT-Madras data) (read 26 Nov 2026, [MODELS.md](MODELS.md)) | in use; **legal confirmation needed** before a commercial launch (NEEDS_APPROVAL item 28) |
| Gemma 4 (E4B, 12B, 31B) | Apache-2.0 (tag; text itself not read) | in use (E4B) |
| Whisper (Apex, large-v3-turbo) | Apache-2.0 / MIT | in use / planned |
| Maya 2 Native | Apache-2.0 | planned |
| Indic-Mio | Apache-2.0 (engine header) | switch, off |
| Silero VAD | MIT (licence file, read 26 Nov 2026) | in use |
| Demucs | code MIT; the maintained repository says "The license of the weights is not clear" (read 26 Nov 2026) | in use; weights unsettled ([OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) question 13) |
| Hosted Gnani and Gemini | vendor terms, not reviewed in our documents | check before launch (unconfirmed) |

## 6. Gaps (SPEC section 20, still open on 25 Nov 2026)

- **No accounts.** Anyone who reaches the site can start jobs and sessions, see `/voices` and `/dashboard`, and open
  a streamer profile by its handle. A voice profile is tied to a person only by its consent record.
- **No terms or privacy pages.**
- **No takedown:** no way for a third party to report a misused voice or video.
- **No HTTPS or domain** (NEEDS_APPROVAL item 13); the site is reached on localhost or through SSH forwards. A demo
  password exists only in the unrun Caddy profile.
- **No monitoring or alerts.**
- **Recordings:** deleted by themselves after 30 days and deletable one by one since 26 Nov 2026
  ([ADR-0034](adr/0034-recording-retention.md)). Still a gap: anyone who reaches the console can delete one (no
  accounts), and deleting a voice does not delete the recordings spoken in it (NEEDS_APPROVAL item 25).
