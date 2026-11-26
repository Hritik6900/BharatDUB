# ADR-0034: Kept Live recordings: 30 days, then deleted; any one deletable at once

- **Status:** accepted
- **Date:** 2026-11-26
- **Superseded by:** —

## Context

A Live session's dub is kept on disk only with `V1_LIVE_RECORD` on **and** the session's own ask
([ADR-0032](0032-opt-in-live-recording.md)). What was kept stayed for good: nothing deleted a recording by itself, and
the only way to remove one was to delete its folder by hand (`../../v1/NEEDS_APPROVAL.md` item 25, 25 Nov 2026). A
recording holds a speaker's copied voice and their words; uploads are deleted after 24 hours (`../../../SPEC.md`
section 15). The founder decided on 26 Nov 2026: recordings are opt-in only, deleted automatically after 30 days by
default, and the user can delete any recording.

## Options considered

| Option | What it is | Why it won or lost |
|---|---|---|
| Keep until someone deletes the folder | as built in WS4 | rejected by the decision above |
| The uploads rule (24 hours) | one rule for everything kept | not chosen: a pitch video is made days after the session (not evaluated further; the number is a setting) |
| 30 days after the recording ended, checked by the backend itself, plus a delete call and a list | **chosen** | the decision; no new moving part (the backend already sweeps uploads every half hour) |
| A scheduled task outside the backend | a script run by the system | not evaluated: one more thing to install and forget |
| Delete a voice profile => delete the recordings spoken in it | a second rule | **not built**: no such rule was given, and a recording does not say whose voice it holds |

## Decision

- `V1_RECORD_KEEP_DAYS` (default 30; `0` = never by itself). A recording is deleted when it **ended** more than that
  many days ago: `ended_at` in its `session.json`, else `started_at` (a backend that died while recording), else the
  newest file in the folder.
- The check (`app/v1/record.py`, `sweep`) runs when the backend starts and every half hour while it runs, in the
  same round as the uploads sweep (`app/main.py`). It runs whether or not `V1_LIVE_RECORD` is on at that time: what
  was kept earlier must still go. A session that is being recorded now is never touched.
- `GET /api/v1/recordings`: what is kept (session, dates, languages, size, the day it goes; no caption text, no
  sound). `DELETE /api/v1/recordings/<session>`: one recording at once; 404 for an unknown name, 409 while that
  session is still recording. The name must be a folder name of ours (letters, digits, `_`, `-`): never a path.
- `/live` lists the kept recordings with a Delete button whenever one exists, and the tick's text says how long a
  recording stays.
- Recording itself is unchanged: still the flag and the session's own tick.

## Consequences

### Good

- Nothing kept for a pitch outlives 30 days by neglect, and one can be removed without touching the server's disk.
- Covered by tests (`backend/tests/test_v1_record_keep.py`): the age rule and its fallbacks, the setting, a live
  recording left alone, the start-up and half-hourly round, list and delete over the API, names that are paths
  refused, flag off still swept.

### Bad

- There are no accounts: anyone who reaches the console can list and delete recordings, as they can voices.
- Deleting a voice profile still does not delete recordings spoken in it (open, item 25). To build it the recording
  must first store the voice profile's id.
- A video rendered from a recording (`data-v1/pitch/`) is a separate file and is not covered: delete it by hand.
- A backup taken before a deletion still holds the recording (the backup script does not copy recordings today:
  `../../v1/RUNBOOK.md` section 7 lists what it copies).
- The backend must run for the rule to act; a server that is off deletes nothing until it starts.
- Not measured: nothing here needed a measurement. The list was not looked at in a browser (type check only).

## Evidence

- Experiments: none (a rule, not a measurement)
- Commits: see `../history/` (v1.2 Part 1)
- Sources: [`NEEDS_APPROVAL.md`](../../v1/NEEDS_APPROVAL.md) item 25; [`RUNBOOK.md`](../../v1/RUNBOOK.md) section 3
  ("How long a recording stays"); [`SPEC.md`](../../../SPEC.md) sections 10 and 15; [ADR-0032](0032-opt-in-live-recording.md)
