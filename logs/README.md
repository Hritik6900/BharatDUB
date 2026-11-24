# logs

The records of every test run on this machine: what was called, how long each step took, how each run ended.
Measurements only. Nothing that was said is kept here: no source text, no translation, no audio, no voice
sample, no key, no voice or token id.

| Folder | What | Written by | Versions |
|---|---|---|---|
| `api/<date>/<test>.jsonl` | one line per outbound request to a provider: which call, host and path, status, ms, attempt, bytes out and in | the v1 backend while it runs, with `V1_API_LOG=true` | v1 |
| `sessions/<version>/<date>_<session>.jsonl` | one line per Live phrase and language: ms for hearing, translation, voice, first audio, how late, speed-up, copied or stock voice, our GPU or hosted, skipped and why | `scripts/v1/collect-logs.py` | v0, v1 |
| `sessions/index.csv` | one row per Live session and language: the numbers of that run | `scripts/v1/collect-logs.py` | v0, v1 |
| `jobs/index.csv` | one row per Studio job: seconds per stage | `scripts/v1/collect-logs.py` | v0, v1 |
| `trace/trace-<date>.jsonl` | v1's trace: per Live phrase and Studio line, which provider did each step and whether a fallback answered | the v1 backend (`V1_TRACE=true`), copied here by the collect script | v1 |
| `streams/` | the stream watcher's files: `events.log`, a row every 20 s per stream, a summary when a stream ends | `scripts/v1/stream-watch.ps1`, copied here by the collect script | v0, v1 |

`<test>` in `api/` is `live_<session>` or `job_<job>` (first 8 characters of the id), or `other` for a call made
outside a session or job. The same 8 characters name the session in `sessions/` and `streams/`, so the three can
be read side by side.

## Keeping it up to date

```powershell
# from the v1 checkout; reads both stores, writes only into logs/
backend\.venv\Scripts\python.exe scripts\v1\collect-logs.py `
    "v0=$env:USERPROFILE\Desktop\BharatDUB\backend\data\local_db.json" "v1=data-v1\local_db.json"
git add logs; git commit -m "logs: tests up to <date>"; git push origin v1
```

`api/` fills by itself while v1 runs. v0 has no per-request log: its code is not changed, so for v0 the finest
record is the per-phrase one in `sessions/`.

## Reading a record

`api/` (one request; this one is the warm-up's translation call on 24 Nov 2026):

```json
{"ts": "2026-11-24T09:52:47.764+00:00", "test": "other", "api": "llm.chat", "method": "POST", "host": "127.0.0.1:9020", "path": "/v1/chat/completions",
 "status": 200, "ms": 519, "attempt": 0, "bytes_out": 652, "bytes_in": 701, "ok": true, "error": null}
```

`attempt` over 0 is a retry (a 429 back-off counts). `status` null with an `error` means no answer came.
The realtime speech-to-text socket and streamed stock voice are one long connection, not a call per line, and
are not in `api/`; their timing per phrase is in `sessions/` and `trace/`.

`sessions/` (one phrase in one language), all times in ms:

| Field | Meaning |
|---|---|
| `speech_ms` | how long the phrase took to say |
| `stt_ms` | end of the phrase to its text |
| `translate_ms` | text to translation |
| `voice_ms` | translation to the first dubbed audio |
| `audio_ms` | first to last audio sent |
| `first_audio_ms` | end of the phrase to the first dubbed audio |
| `heard_ms` | end of the phrase to when a viewer starts hearing it (the server's estimate) |
| `late_ms` | sync mode: how long after its video moment the dub starts |
| `tempo` | speed-up applied to fit (1.3 is the limit) |
| `copied_voice`, `on_gpu` | 1 when the line was in the copied voice, and when our GPU engine made it |
| `skipped` | `unheard` (no viewer on that language), `late` (too late to be worth saying) |
| `dub_ms`, `dub_raw_ms` | v1.1: the dubbed audio that was sent, and the same line at the voice's own pace (before any speed-up) |
| `slot_ms`, `dur_ratio` | v1.1: the span of the source phrase (of all of them when several were spoken in one call: then only the first of them has these fields), and `dub_ms / slot_ms` |
| `backlog_ms` | v1.1: how far the dub queue was behind the video when this phrase's turn came |
| `tgt_words`, `tgt_chars` | v1.1: length of the translated line in words and in letters (no text) |
| `budget_ms`, `budget_scale`, `reasked` | v1.1 with `V1_LIVE_BUDGET`: the duration the translator was given, the controller's scale, 1 = a shorter line was asked for, 2 = and used |

`sessions/ws2-*/` and `trace/ws2-*/` are the comparison backends of the v1.1 WS2 measurement (`docs/v1/PROGRESS.md`):
`ws2-off` and `ws2-warm`, `ws2-warm2` (session start: off, the first build, the final build), `ws2-en-off`,
`ws2-en-copy`, `ws2-en-stock` (English voice: flag off, every line in the hosted copy, every line in one stock
voice; `ws2-off` also holds the one flag-off session of a first English attempt that was stopped). In those, a line with `copied_voice` 0 or 1 and no `first_audio_ms` and no `skipped` is one the hosted
voice refused (25 Nov 2026: HTTP 502 on many stock lines).

The v1.1 fields are in a record only where they were measured (a backend with the trace or the dense-speech
flags on, from 24 Nov 2026). `sessions/ws1-*/` and `trace/ws1-*/` are the comparison backends of the v1.1 WS1
measurement (`docs/v1/LIVE_DENSE_REPORT.md`): off, budget, ctl (budget + controller), native, tight.

`audio_ms` is NOT the length of the dub: a line from our voice engine is sent in one piece (about 0 ms) and a
streamed stock voice arrives faster than it plays. Before v1.1 the dub's length was not stored at all; for older
sessions it can only be worked out for a phrase whose successor queued straight behind it (the next phrase's
`heard` time minus this one's), which is what `backend/eval/v1/expansion_seed.py` does. From v1.1 on `dub_ms` is exact.

With `V1_BREAKER` and `V1_LIVE_DEGRADE` on (v1.1), `streams/events.log` also has `CIRCUIT OPEN <endpoint>: <why>`,
`CIRCUIT CLOSED <endpoint> after <n> s`, `CIRCUIT LINK STALL`, `CIRCUIT LINK BACK` and
`RUNG [backend session] a -> b (why)`; the trace has `circuit` and `live_degrade` events, and each stored Live
phrase has `rung:<lang>` (0 copied voice, 1 stock voice, 2 no voice, 3 not translated).
