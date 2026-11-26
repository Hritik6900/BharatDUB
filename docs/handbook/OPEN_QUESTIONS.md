# Open questions

Numbered questions that block a decision or a claim. Dated 2026-11-25; questions 3, 7, 13, 18 and 20 updated and
question 21 added on 2026-11-26 (v1.2 Part 1). A closed question keeps its number. Sources: `docs/v1/SUMMARY.md` section 4,
`docs/v1/V1_1_SUMMARY.md` sections 3-4, `docs/v1/NEEDS_APPROVAL.md` (current item numbers), `docs/v1/MODELS.md`,
SPEC sections 20-21. Owner: **founder** (a decision, a recording, a price, a listener) or **engineering** (a run
or a build). Plan view: [ROADMAP.md](ROADMAP.md).

## Product and decisions

### 1. Which Live flags go on?
- **Why it matters:** the budget lifts within 1 s from 86.5% to 92.3% on dense speech, but in Tamil 7 of 20 lines
  read lost something that mattered, and it is one switch for every language. Breaker + ladder kept every phrase
  dubbed through a 50 s stall (4 of 22 without).
- **What would answer it:** the founder's call on the measured picture; a per-language budget would remove the
  Tamil trade-off (not built); a native Tamil reader on more lines.
- **Owner:** founder. **Blocked on:** nothing (item 24 lists it).

### 2. Which English voice, and may a session switch to the copy when the stock voice fails?
- **Why it matters:** `auto` (one stock voice) is on time; `copy` keeps the speaker's voice in English but every
  line was 13 points worse within 1 s on the dense reel. On 25 Nov the stock voice refused 59% of its lines.
- **What would answer it:** listening to both (`--keep-audio` run), a healthy-night measurement.
- **Owner:** founder. **Blocked on:** item 22 (and 19 c for the healthy night).

### 3. May Studio HQ be offered without `V1_HQ_REVIEW`? Is our Whisper's second hearing worth keeping?
- **First half answered, 26 Nov 2026 (founder): no.** HQ never runs without the review, and the code enforces it:
  an HQ job is reviewed and its transcript guarded whatever `V1_HQ_REVIEW` says (`app/v1/hq/review.py`, tested).
  The second half (the second hearing) stays open.
- **Why it matters:** without the review two of three test videos were dubbed from a damaged transcript; the
  second hearing is where the Latin-letter lines came from, and the hosted hearing measured better.
- **What would answer it:** an HQ run with the hosted hearing only, compared line by line with the review on.
- **Owner:** founder (offer), engineering (run). **Blocked on:** none for the run; item 24 for the decision.

### 4. What should "96% heard back" mean?
- **Why it matters:** the judge counts a spelling it writes differently as a word not heard, and a dub of the wrong
  sentence as heard. Neither the 96% target nor the 0.9 flag line is tied to what a listener hears.
- **What would answer it:** 30 labels per language with 5 of each kind on `/studio/calibrate`, from a speaker of it.
- **Owner:** founder (labellers). **Blocked on:** item 21.

### 5. Where does v1 run?
- **Why it matters:** every Live phrase crosses the tunnel several times; v0 measured first audio p50 2.3 s through
  it vs 1.8 s on the VM (one run each). No v1 number should be quoted as the product's until it runs there.
- **What would answer it:** move the backend (item 2) and repeat `EVAL_REPORT.md` section 1 once.
- **Owner:** founder (approve), engineering (run). **Blocked on:** items 1-2.

### 6. Should `V1_LIVE_STOCK_DEFAULT` be on?
- **Why it matters:** on, a `/live` session without a streamer profile never learns a voice; the only v1 stock-voice
  runs had first audio p50 5.1 s and 58.3% within 1 s against 2.34 s and 83.3% with the learned voice. The budget was
  never measured with stock voices; `V1_PHRASE_DYNAMIC` gained only when a voice is ready at the start.
- **What would answer it:** a stock-voice run with the budget and with `V1_PHRASE_DYNAMIC`.
- **Owner:** founder (rule), engineering (run). **Blocked on:** none.

### 7. How long are recordings kept, and does deleting a voice delete them?
- **First half answered and built, 26 Nov 2026 (founder):** recording stays opt-in; a recording is deleted by
  itself 30 days after it ended (`V1_RECORD_KEEP_DAYS`, checked when the backend starts and every half hour); the
  user can delete any recording (`/live` list, `DELETE /api/v1/recordings/<session>`). [ADR-0034](adr/0034-recording-retention.md).
- **Still open: does deleting a voice delete the recordings spoken in it?** Today it does not, and it could not:
  a recording does not say whose voice it holds (`session.json` has no voice or streamer id), and deleting a voice
  profile removes the sample and the embedding only. No rule was given, so none was built.
- **What would answer it:** the founder's rule; then the recording has to store the voice profile's id.
- **Owner:** founder. **Blocked on:** item 25.

### 8. What does a dubbed minute cost, and what is the price?
- **Why it matters:** no price without it (SPEC section 20). `/metrics-ui` shows cost only for the rates set; all
  are 0. The pitch document's cost figures are **stand-in** prices.
- **What would answer it:** real hourly A100 rate and the hosted vendors' prices.
- **Owner:** founder. **Blocked on:** item 23.

## Models and licences

### 9. Indic Transcribe: sign-off or samples only?
- **Why it matters:** hosting it as a service others call needs its authors' written sign-off.
- **What would answer it:** the sign-off, or a decision to keep the hosted speech-to-text.
- **Owner:** founder. **Blocked on:** item 11 (and item 24).

### 10. Does the 12B translation model win, and does it start on our vLLM?
- **Why it matters:** Studio HQ translation; the checkpoint's page reports start failures with no working vLLM
  version named; 31B does not fit by the estimates.
- **What would answer it:** `smoke.sh big-llm`, then the A/B with its rule fixed beforehand (preferred in 60% of at
  least 40 decided pairs, no language under 50%, no more wrong-script lines, not longer, median 2.0 s a line).
- **Owner:** engineering (run), founder (blind sheet). **Blocked on:** item 9.

### 11. Maya 2: keep or drop?
- **Why it matters:** it would give English in the speaker's own copied voice; it has no speed control.
- **What would answer it:** the 20-line voice A/B and the listening page.
- **Owner:** founder (ears), engineering (deploy). **Blocked on:** items 8, 26.

### 12. Where is the speaker-similarity threshold on the new scale?
- **Why it matters:** earlier numbers used ECAPA2 (non-commercial) and do not carry over; the new model gave 0.88
  for one speaker against themselves (7 s cuts) and 0.14 against another voice, one pair each.
- **What would answer it:** the founder's recorded voice against itself and its copies on the QA server.
- **Owner:** engineering. **Blocked on:** item 4.

### 13. Do the speaker model's training data, Demucs' weights and the hosted vendors' terms allow commercial use?
- **Why it matters:** the speaker model is Apache-2.0 but trained on VoxCeleb (no licence stated). The hosted
  vendors' terms were never reviewed.
- **Recorded on 26 Nov 2026 from the official repositories** ([MODELS.md](MODELS.md), `../v1/MODELS.md`):
  Silero VAD is MIT (licence file; its README: "Published under permissive license (MIT)"). Demucs' code is MIT
  in both repositories, but the maintained one's README says of the weights: "The license of the weights is not
  clear: MusDB contains some data that were only usable for research purpose." So Demucs is **not** settled by
  its MIT file. IndicF5 moved to question 21.
- **What would answer it:** a legal read before a contract; for Demucs, a separation model whose weights carry a
  clear licence, or a lawyer's view on the weights.
- **Owner:** founder. **Blocked on:** item 24.

## Engineering

### 14. Does the copied voice sound like the speaker?
- **Why it matters:** only machine measures exist (words heard back, speaker similarity); nobody has listened in a
  blind test.
- **What would answer it:** about 20 pairs a language and five listeners on `/listen-test`.
- **Owner:** founder (listeners). **Blocked on:** items 8, 26.

### 15. How does Live behave on a long, real, dense stream?
- **Why it matters:** the dense-speech numbers come from one 24.9 s reel played 8 times.
- **What would answer it:** 2-3 dense 10-minute recordings through the replay harness.
- **Owner:** founder (recordings). **Blocked on:** item 20.

### 16. Does the session warm start help, with a recorded voice and a male speaker?
- **Why it matters:** no proven gain on the measured case; the untested cases are where it might matter.
- **What would answer it:** the runs listed in item 19.
- **Owner:** engineering + founder (a voice recorded in v1 with consent). **Blocked on:** item 19.

### 17. Can one GPU or one hosted account carry two streams?
- **Why it matters:** capacity (SPEC section 20). One test run beside a real stream cut it to 56% within 1 s; whether
  the hosted account allows two realtime speech-to-text sockets is not known.
- **What would answer it:** a planned two-stream run with the backend on the VM; the vendor's account limits.
- **Owner:** engineering. **Blocked on:** items 1-2.

### 18. How should the hold come back down after a stall? (server side built 26 Nov 2026; browser test open)
- **Why it matters:** on the 67-minute stream it grew from 6 s to 11 s and stayed; a viewer's player leaves a small
  offset alone, so lowering it on the server would not move viewers already watching.
- **Built and measured on 26 Nov 2026** ([ADR-0035](adr/0035-hold-ease-back.md),
  [EXP-030](experiments/EXP-030-hold-ease-back.md)): the server gives the hold back in steps of 250 ms once phrases
  have time in hand again (after a slow link of 70 s: 11.0 s with the rule off at the end of both runs; 6.25 s
  and 6.0 s with it on, 2 runs each), and the viewer page plays 1.1x after each step until it has caught up.
  Kill switch `LIVE_SYNC_EASE=false`.
- **Still open:** the viewer page's catch-up was type-checked, not run in a browser. Whether a YouTube embed (a
  live one above all) takes the 1.1x is not known.
- **What would answer it:** a browser test of `/watch` through a slow spell, on an uploaded video and on a live
  broadcast (`window.__bdSync` shows where the player is against where it should be, and its speed).
- **Owner:** engineering. **Blocked on:** none (it needs a browser test set up in `web/`, and the website rebuilt).

### 19. Does the restore from backup work, and do the engines come back warm in 5 minutes?
- **Why it matters:** the restore was never rehearsed and the engines do not start by themselves.
- **What would answer it:** a bucket, one backup, one restore on another machine; a timed VM restart.
- **Owner:** founder (bucket, snapshot), engineering (rehearsal). **Blocked on:** items 15, 1-3.

### 20. Should `V1_HQ_ADAPTIVE` be on? (closed 26 Nov 2026: on)
- **Answer (founder, 26 Nov 2026): on.** The four places now say the same thing with the same measured reason:
  against five takes of every line 61% less voice time (206 s against 524 s over three videos) with the same take kept on 76 of 76 lines; against v1's earlier rule (up to 4 takes until one passes) the same number of takes (143), so it costs nothing.
  The code's default is on as well (it acts on HQ jobs only); tests and comparison backends still force it off
  unless a test or a run asks for it. NEEDS_APPROVAL item 27, point 1, is closed.
- **As it stood on 25 Nov:** the sources disagreed. `docs/v1/V1_1_SUMMARY.md` section 3 says on (61% less voice time
  against five fixed takes, the same take kept on 76 of 76 lines); `docs/v1/RUNBOOK.md` section 3,
  `docs/v1/SUMMARY.md` and `backend/.env.example` say off (against v1's own rule both make 143 takes).
- **What would answer it:** the founder's choice; no new measurement is needed. Then make the four places agree.
- **Owner:** founder. **Blocked on:** nothing (closed).

### 21. Is IndicF5 open to commercial use? Status: **legal confirmation needed** (26 Nov 2026)
- **Why it matters:** IndicF5 is the copied voice of the product (in use on 9001-9003). Two sources say two things.
- **Source A, MIT:** the model's Hugging Face record has `license: mit` (https://huggingface.co/ai4bharat/IndicF5,
  API record read 26 Nov 2026, revision `fb652a96e508091045890dae5bb99fe511facbcf`, gated). Its page says nothing
  about commercial use; its terms of use are about consent ("only clone voices for which you have explicit
  permission"). Its GitHub repository (https://github.com/AI4Bharat/IndicF5) has no licence file.
- **Source B, non-commercial lineage:** the card of a model fine-tuned from it, `dheeyantra/dhee-indic-f5`
  (https://huggingface.co/dheeyantra/dhee-indic-f5, CC-BY-NC-4.0, read 26 Nov 2026), says: "This model inherits
  non-commercial terms from its lineage: it is fine-tuned from `ai4bharat/IndicF5`, which builds on **F5-TTS**
  (trained on the **Emilia** dataset, CC-BY-NC-4.0) and **IIT-Madras Indic TTS** data (non-commercial)." The same
  card lists its base model as "`ai4bharat/IndicF5` (MIT)". F5-TTS's own pages agree on its half: "The pre-trained
  models are licensed under the CC-BY-NC license due to the training data Emilia"
  (https://github.com/SWivid/F5-TTS, README; Hugging Face tag `cc-by-nc-4.0`).
- **Not known:** whether IndicF5's weights started from F5-TTS's pre-trained (Emilia) weights or were trained from
  nothing on the data AI4Bharat lists (Rasa, IndicTTS, LIMMITS, IndicVoices-R): neither AI4Bharat page says. The
  terms of the IndicTTS and LIMMITS data were not read. The third party's claim is a claim, not a ruling.
- **What would answer it:** written confirmation of commercial use from AI4Bharat, or a legal review.
- **Owner:** founder. **Blocked on:** item 28.
