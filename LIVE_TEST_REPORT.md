# Live mode: end-to-end test, 13 Nov 2026

Everything below was measured on the real Gnani and Gemini APIs, through the running backend, the same way a
streamer and a viewer use it. No number here is estimated.

## What was tested, and what was not

- **Source "stream":** the audio of your own uploaded reel (`WhatsApp Video 2026-11-13 at 15.21.13`, 24.9 s, Hindi,
  one speaker), played into `/ws/ingest` at real-time speed, 2 or 3 times in a row. This is exactly what the mic
  client sends.
- **I did not copy the voice of a stranger's live stream.** Cloning needs the speaker's consent (rule 4 in
  SPEC.md), and a random streamer has not given it. Your reel already had your consent on record, so it was used.
- A real YouTube live link (NASA's live channel) was used only to check that the viewer page embeds and plays a
  live video. It plays.
- This reel is a hard case: the speaker talks without pauses, so a 6-second line arrives every 6 seconds.
  A streamer who pauses gives the system more room.
- I cannot listen. Whether the copied voice sounds like you is the one thing you have to judge by ear
  (files listed at the end).

## New in this session

1. **Live learns the voice from the stream itself.** On `/live`, the default voice is now "The voice on this
   stream". Tick the consent box, go live, and after 12 seconds of speech the dub switches from a stock voice to
   the speaker's own voice. Without the consent tick the backend refuses (HTTP 403). The copy is saved under
   Your voice and can be deleted there.
2. **Translation no longer waits behind the previous line's audio.** Captions arrive sooner.
3. **The dub keeps pace.** Stock voices speak 15% faster in Live, the translator is told to be brief, and the
   viewer's player speeds up 10% when more than 2 s of audio is waiting (and skips a line that is over 10 s late).
4. **Own voice in one language at a time.** See "The limit" below.

## Results

"First audio" is the time from the end of a spoken line to the first dubbed audio leaving the server.
"Heard" is when the viewer actually starts hearing that line, counting earlier lines that are still playing.

| Run | Voice | Languages | Lines | First audio p50 / p95 | Heard p50 / p95 / worst | Lines in own voice |
|---|---|---|---|---|---|---|
| S3 | Stock | Tamil, Bengali, English | 10 | 3.6 s / 4.7 s | 4.3 s / 9.4 s / 11.6 s | none (by design) |
| V1 | Your saved voice | Tamil | 10 | 4.6 s / 5.4 s | 4.8 s / 7.3 s / 7.7 s | 10 of 10 |
| V3 | Your saved voice | Tamil, Bengali, English | 10 | 5.4 s / 8.8 s | 6.9 s / 11.8 s / 14.2 s | Tamil 10 of 10; Bengali, English stock |
| L1 | Learned from the stream | Tamil | 15 | 4.3 s / 5.6 s | 4.6 s / 8.2 s / 8.3 s | 9 of 15 (first 6 were before the voice was ready) |
| L3 | Learned from the stream | Tamil, Bengali, English | 15 | 4.9 s / 7.6 s | 6.6 s / 11.2 s / 14.1 s | Tamil 10 of 15; Bengali, English stock |

- **No errors** in any run: no failed line, no dropped connection, no line skipped by the player.
- **Learning the voice from the stream** took 33 to 37 s from the start of the stream (12 s of speech collected,
  then about 1.4 s to make the copy).
- **Where the time goes** for one line: about 0.5 s for speech-to-text, 1.5 to 1.7 s for translation, then
  0.4 to 0.5 s for a stock voice to start, or 1.9 to 3.5 s for the copied voice (it arrives all at once, not as a stream).
- **Viewer chat:** a Tamil message reached the streamer translated into Hindi in 1.2 to 2.2 s.
- **Viewer page in a real browser (Edge, phone width):** captions, audio frames, chat and the live badge all
  worked, with no console errors and no sideways scroll. Screenshot: `backend/scripts/out/live/L1_stream_1lang/watch_mobile.png`.

### Before and after today's fixes (same reel, same languages)

| | Before | After |
|---|---|---|
| Stock, 3 languages: heard p50 / worst | 11.3 s / 37.8 s | 4.3 s / 11.6 s |
| Your voice, 3 languages: first audio p50 | 22.3 s, and growing with every line | 5.4 s, stable |
| Your voice, 1 language: first audio p50 | 5.2 s | 4.6 s |

## The limit: own voice in one language

- The Gnani account runs **one request at a time**. I sent three at once and two were refused
  ("Only 1 active request is allowed at a time").
- A line in the copied voice takes 2 to 4 s to make; a stock line starts in about 0.5 s.
- So three languages in the copied voice cannot keep up: before the fix, the dub was 37 s behind after 55 s.
- Now the first language you pick is dubbed in the speaker's own voice and the others use stock voices. If a line
  is already more than 5 s late, that one line falls back to the stock voice to catch up.
- If Gnani raises the limit, set `GNANI_MAX_CONCURRENCY` to the new number and that many languages get the own voice.
  Worth asking them on Discord before the demo.

## Does it say the right words?

Every dubbed line was sent back through speech-to-text and compared with the text it was meant to say.

| Language | Own voice | Stock voice |
|---|---|---|
| Tamil | 85 to 87% of words match | 87 to 89% |
| Bengali | not run in own voice | 86 to 87% |
| English | not run in own voice | 98 to 99% |

The copied voice is as clear as the stock voice in Tamil. Part of the mismatch is the speech-to-text itself
(spelling of English words inside Tamil and Bengali).

## Does it sound like you?

Not proven. The only automatic check available was speaking pitch: your reel is around 219 Hz, the own-voice
Tamil dub around 190 Hz, the stock Tamil voice around 240 Hz. Pitch alone does not settle it. Please listen:

- Own voice, learned live: `backend/scripts/out/live/L1_stream_1lang/dub_ta-IN.wav` (lines 7 to 15 are your voice; 1 to 6 are stock)
- Own voice, saved profile: `backend/scripts/out/live/V1_saved_1lang/dub_ta-IN.wav`
- Stock, for comparison: `backend/scripts/out/live/S3_stock_3lang/dub_ta-IN.wav`
- Your original: `backend/data/jobs/45f013a9…/voice_sample.wav`

## Not tested

- A real microphone and a human speaking live (the audio came from a file).
- A real phone on a real network; a second viewer at the same time.
- Sessions longer than 82 s (the 15-minute speech-to-text reconnect was not reached).
- Music or game sound behind the voice while the voice is being learned.

## Run it again

```
cd backend
python scripts/live_e2e.py <video> scripts/out/live --name mytest --voice stream --langs ta-IN --loops 3
python scripts/live_analyze.py scripts/out/live mytest
python scripts/live_quality.py scripts/out/live <voice_sample.wav> mytest
```

`--voice` is `stock`, `stream`, or a saved voice id. Raw numbers: `backend/scripts/out/live/results.json` and `quality.json`.
