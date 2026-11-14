# Live mode: measured results, 14 Nov 2026

Everything below was measured on the real Gnani and Gemini APIs, through the running backend, the way a streamer
and a viewer use it. No number here is estimated, except where a line says so.

## Read this first

- **The number that matters is "heard".** Until 13 Nov this report gave "first audio": the time from the end of a
  spoken line to the first dubbed audio leaving the server. A viewer hears a line only after the earlier lines have
  finished playing, so the real delay is longer. The server now estimates that moment for every phrase, and an
  offline replay of the web player's own rules agrees with it to within 0.1 s on the single-viewer runs.
- **The 13 Nov numbers were about 0.3 to 0.6 s too kind.** They took the end of speech as "final transcript minus
  0.5 s". Gnani's own `speech_end` event (found on 13 Nov) shows speech ends earlier than that.
- **Source "stream":** the audio of your own reel (24.9 s, Hindi, one speaker, about 4.5 words a second with no
  pauses), fed in real time, 2 or 3 times in a row. That is a hard case: a streamer who pauses gives the system room.
- **Not tested:** a real microphone with a person speaking live, a real phone on a real network, a session longer
  than 82 s, music or game sound behind the voice. I cannot listen, so how the dub sounds is yours to judge.

## Results (stock voices unless said)

"Heard" = end of a phrase to the moment the viewer starts hearing its dub. "From first word" = from the first word of
the phrase instead of its end.

| Run | Viewers on | Phrases | First audio p50 / p95 | Heard p50 / p95 / worst | From first word, heard p50 / p95 | Skipped |
|---|---|---|---|---|---|---|
| 4 languages offered | Tamil | 26 | 2.7 s / 3.6 s | 3.4 s / 5.8 s / 5.9 s | 4.8 s / 6.9 s | 0 |
| 3 languages offered | Tamil | 26 | 3.5 s / 5.0 s | 4.4 s / 5.8 s / 6.2 s | 5.7 s / 7.3 s | 0 |
| (same run) | Bengali | 26 | 3.8 s / 4.7 s | 6.0 s / 7.5 s / 7.5 s | 7.2 s / 8.9 s | 0 |
| (same run) | English | 26 | 3.5 s / 4.9 s | 3.9 s / 5.5 s / 5.6 s | 5.2 s / 7.1 s | 0 |
| Voice learned from the stream, 4 offered | Tamil | 38 | 2.6 s / 3.5 s | 3.5 s / 6.7 s / 7.1 s | 4.9 s / 7.6 s | 3 |

- In the learned-voice run 14 of 38 phrases were in the speaker's own voice. The first 12 came before the voice was
  ready; later ones fell back to the stock voice whenever the dub was already more than 5 s behind.
- No errors and no dropped connection in any run. The viewer page in a real browser (Edge, phone width) played 398
  audio frames with captions, no console errors, no sideways scroll, and its badge showed "Dub delay 3.4 s".

### What a viewer got before (same reel, Tamil, one viewer)

| | 13 Nov evening (whole lines) | 14 Nov, phrases only | 14 Nov, final |
|---|---|---|---|
| Heard p50 / p95 | 3.4 s / 7.1 s after a line of about 5 s | 7.8 s / 11.1 s | 3.4 s / 5.8 s after a phrase of about 1.2 s |
| Phrases skipped by the player | 0 of 10 | 1 of 25 | 0 of 26 |

The middle column is why "first audio" was the wrong number to watch: cutting speech into short phrases brought first
audio down to 2.3 s, but the Tamil dub came out 28% longer than the speech (64.4 s of audio for 50.3 s of talking), so
audio piled up in the player and viewers heard it later, not sooner.

## What changed on 13 and 14 Nov

1. **Phrases instead of whole lines.** Gnani's realtime speech-to-text has an undocumented switch (`x-partials: true`)
   that sends the text so far about twice a second, with the part it will no longer change. Phrases of 6 to 12 words
   are cut from that at clause boundaries, so translation and voice start while the speaker is still talking.
2. **The dub no longer piles up.**
   - The silence Timbre puts before and after every phrase is cut (it was about 0.27 s a phrase).
   - When audio is still waiting to be played, the next phrase is shortened by up to 1.3x with ffmpeg `atempo`
     (speed only, the pitch stays). In the single-viewer run this was applied to 21 of 26 phrases: this speaker is fast.
   - A phrase that would be heard more than 8 s late is not spoken; its caption still goes out.
3. **One voice call for several waiting phrases.** The Gnani account runs one request at a time. Phrases that queue up
   behind it are now spoken in a single call (up to 3), which is what keeps three viewer languages from falling behind.
4. **Audio only for languages someone is listening to.** Captions go out for every language.
5. **Faster translation.** `gemini-3.1-flash-lite` for Live: 0.82 s a phrase against 1.02 s for `gemini-3.5-flash`
   (48 phrases each, `scripts/live_llm_bench.py`). About 1 reply in 20 from the Flash models carries a word in the
   wrong script (Devanagari, once Georgian, inside a Tamil line); such a reply is redone by the main model.
6. **Source language is fixed per session** (Hindi/Hinglish by default). Auto-detect over game sound produced Bengali
   and Kannada lines.
7. **Sound can come from a browser tab** on the Live console (tab only; a window or screen share is refused because it
   carries the dub back in and loops).
8. The delay badge on the viewer page and the console now shows "heard", not "first audio".

Every one of these has a switch in `backend/app/config.py` (`LIVE_PARTIALS`, `LIVE_FIT`, `LIVE_TRIM_SILENCE`,
`LIVE_MERGE_MAX`, `LIVE_TTS_ONLY_HEARD`, `LLM_MODEL_FAST`), so any of them can be turned off without touching code.

## Sync mode: picture and dub together (14 Nov, afternoon)

The viewer no longer has to hear the dub a few seconds after the picture. When the console plays the stream's video
itself (Sound from: the video on this page), it reports the video's time. Each dubbed phrase is tied to the video
moment it was spoken at, and the viewer page holds its own player a few seconds behind, so a phrase is heard while
the picture shows the speaker saying it. The delay starts at 6 s and grows by itself to what the dub needs.

Same reel, Tamil, stock voice, three loops (82 s), real APIs. "Behind" is how long after its video moment a phrase
started; 0 means exactly on it.

| Run | Delay viewers were held at | Behind p50 / p95 / worst | Skipped |
|---|---|---|---|
| APIs fast | 8 s | 0.3 s / 1.9 s / 2.2 s | 1 of 39 |
| APIs slow (voice calls 2.5 to 4 s) | 10 s | 0.6 s / 2.8 s / 3.9 s | 0 of 38 |
| Voice learned from the stream, APIs slow | 14.5 s | 1.2 s / 2.6 s / 3.2 s | 0 of 38 |

- In a real browser (Edge) the viewer's video stayed 0.1 to 2.6 s behind its target and 15 of 18 phrases arrived
  before their moment. The console capturing its own tab was checked in a visible Edge window: 11 lines heard in 36 s.
- What is behind is the dub's length, not its making: this speaker never pauses, and Tamil at 1.3x speed is still as
  long as the Hindi. While a language is behind, the translator is asked for a shorter version of the next phrase.
- **The copied voice does not keep up here:** 5 of 21 spoken phrases were in the copied voice. A cloned line takes
  2 to 3.5 s to make and only one can be made at a time.
- **Gnani and Gemini were slower in the afternoon** than at night: a short Tamil phrase took 2.5 s to voice instead of
  0.9 s, translation 1.2 to 2.3 s instead of 0.8 s. The delay grows to cover it; the numbers above move with it.
- Not tested: a real live YouTube broadcast (only uploaded videos), a phone, a person at a microphone.
- Without sync mode (mic, or another tab) nothing changed in how the dub is played. With the shorter translations the
  same single-viewer run gave heard p50 3.4 s / p95 4.6 s (it was 3.4 s / 5.8 s); three phrases at the very start
  were skipped after the first translation took 4.4 s.

Switches: `LIVE_SYNC`, `LIVE_SYNC_DELAY_MS`, `LIVE_SYNC_ADAPT`, `LIVE_BRIEF`, `LIVE_WARMUP`.

## Limits that code does not remove

- **One Gnani request at a time.** With viewers on three languages, first audio is about 3.5 to 3.8 s instead of 2.7 s,
  and Bengali is heard 6 s behind. A higher account limit would fix this; ask Gnani.
- **The copied voice is slow to make** (1.9 to 3.5 s a phrase, not streamed), so it is used only while the dub is less
  than 5 s behind, and only for the first language.
- **Dense, fast speech does not fit.** Tamil and Bengali take longer to say than Hindi. With this speaker most phrases
  are played 1.3x faster. Please listen to how that sounds.

## Listen

`backend/scripts/out/live/`:

- `J_stock_ta/dub_ta-IN.wav`: stock voice, final settings (phrases, trimmed, sped up where needed)
- `H_stream_ta/dub_ta-IN.wav`: voice learned from the stream (about the last third is the copied voice)
- `H4_stock_4lang_1heard/dub_ta-IN.wav`: 13 Nov, whole lines, for comparison

## Run it again

```
cd backend
python scripts/live_e2e.py <video> scripts/out/live --name mytest --voice stock --langs ta-IN,bn-IN,en-IN --listen ta-IN --loops 2
python scripts/live_player_sim.py scripts/out/live mytest ta-IN     # what the viewer hears, replayed offline
python scripts/live_llm_bench.py gemini-3.1-flash-lite gemini-3.5-flash@none
```

`--voice` is `stock`, `stream`, or a saved voice id. `--listen` is the languages a viewer is tuned to (default: all).
