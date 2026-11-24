# v1 models: what each one is, its licence, its size

Checked on 23 Nov 2026 against the models' own pages (Hugging Face cards and file lists, the code repositories,
the vLLM recipe for Gemma 4). "Not verified" means no primary page stated it. Nothing here was loaded on the GPU:
memory figures are the cards' own, not ours.

## Summary

| Port | Server | Model | Licence | Commercial use | Disk | GPU memory (source) | Fits beside v0 now? |
|---|---|---|---|---|---|---|---|
| 9041 | voice, batching | `ai4bharat/IndicF5` (0.4 B) | MIT, gated (auto) | yes; terms: copy only voices you have permission for | 1.4 GB | not stated; v0's engines hold about 4 GB each as processes | no: under the 4 GB headroom rule |
| 9042 | Maya 2 | `maya-research/maya2-native` (2.5 B) | Apache-2.0, not gated | yes | 5.0 GB | 7.7 GB steady, 9.2 GB while loading, +0.5 GB context (card) | no |
| 9043 | Indic Transcribe | `bodhan-ai/indic-transcribe-core` (1.2 B) | Indic Open Model License v1.0, gated (auto) | **self-hosting yes; a hosted service others call needs written sign-off**; attribution | 4.6 GB (repo 9.8 GB) | 9.2 GiB at batch 8 (card) | no |
| 9044 | big translation model | `google/gemma-4-12B-it-qat-w4a16-ct` or `...-31B-...` | Apache-2.0, not gated | yes | 10.3 GB / 23.3 GB | about 11-14 GB / 20-23 GB + cache (estimate from the weights) | only in an HQ window |
| 9045 | QA: hear back | Whisper large-v3-turbo via faster-whisper | MIT | yes | about 1.6 GB | CPU by default | yes (CPU) |
| 9045 | QA: speaker similarity | `speechbrain/spkrec-ecapa-voxceleb` | Apache-2.0 | yes | small | CPU | yes (CPU) |
| 9045 | QA: diarization | `pyannote/speaker-diarization-community-1` | CC-BY-4.0, gated (accept terms, token) | yes, with attribution | not stated | not stated; runs on CPU | yes (CPU), off by default |

GPU now: v0's servers hold about 34 of 40 GB, so about 6 GB is free, and a new model may load only if 4 GB stays
free afterwards. That allows nothing above 2 GB. Every GPU load below is therefore deferred
(`NEEDS_APPROVAL.md`); the QA server is the exception because it runs on CPU.

## Findings that change the plan

1. **ECAPA2 is non-commercial.** `Jenthe/ECAPA2` is CC-BY-NC-4.0. The voice-similarity numbers measured earlier in
   this project used it. For a product the QA server uses SpeechBrain's ECAPA-TDNN (Apache-2.0); its scores are on
   another scale, so the earlier figures (0.63-0.76 copied voice, 0.86-0.89 the real person) do not carry over and
   the real-person baseline has to be measured again with the new model.
2. **Indic Transcribe's licence** lets a company host it for its own product without a fee, but running it "as an
   API or hosted service that other people or companies call directly" needs the authors' written sign-off, and a
   separate licence applies above 500 M monthly users or 250 M dollars of revenue. Its base model
   (`nvidia/canary-1b-v2`) has its own terms. The full licence text could not be fetched. Fine for samples and a
   pitch; before production either get the sign-off or keep the hosted speech-to-text. Decision for the user.
3. **Maya 2 Native is not served by vLLM.** It has its own engine (package `maya3`) with a Mimi codec, needs the
   reference clip's exact transcript for cloning (as IndicF5 does), and documents no speed or duration control.
   So it cannot fit a line to its slot by itself: in Studio HQ it is a candidate voice whose lines are fitted
   afterwards, and for Live it has no advantage over IndicF5 on timing. Its vendor's speed claim (14 ms to first
   audio, real-time factor 0.13) is for an H100; no A100 figure exists.
4. **The live Whisper server (9030) cannot hear a dubbed line back**: it is a Hindi/Hinglish model. Back-check of
   Tamil, Bengali or Punjabi speech needs the QA server's multilingual Whisper (lower accuracy on the smaller
   languages, by its own card) or the hosted speech-to-text.
5. **IndicF5 as shipped does not batch several lines**: its batch helper loops one line per forward pass. The v1
   voice server batches through the sampler's padded-batch interface; that path was written from the interface
   and has not been run.
6. **Gemma 4 is Apache-2.0** (confirmed on the card). Sizes: E2B, E4B (in use), 12B, 26B-A4B (mixture of experts),
   31B. Google publishes 4-bit QAT checkpoints for vLLM (`...-qat-w4a16-ct`), so no third-party quantisation is
   needed. The vLLM recipe advises against 4-bit for 26B-A4B. The recipe names no minimum vLLM release (it says
   to install a pre-release), so the image tag is left for the user to set. How well the 4-bit models translate
   Hinglish into Indian languages is not verified anywhere: it is measured on our set before it is trusted.
7. **Separation:** Kim's MelBand RoFormer vocals model scores higher than fine-tuned Demucs on a singing benchmark
   (10.98 against 8.78 dB), but no speech-against-music comparison was found and its licence is unsettled (MIT tag
   on Hugging Face, no licence in its code repository, CC-BY-NC-SA according to one third party). Not adopted.

## Per model

**IndicF5** (`ai4bharat/IndicF5`): 11 Indian languages, no English. Speed and duration:
`infer_process(..., speed=1.0, fix_duration=None)`; duration is sized by UTF-8 bytes of the text against the
sample's (v0's engine corrects this to letters); `fix_duration` (sample + new line, in seconds) overrides `speed`.
Studio HQ's "duration control first" uses the speed parameter, which v0's engines already accept.

**Maya 2 Native** (`maya-research/maya2-native`, checkpoint 1.0 of 25 Oct 2026, card revision `87a83efd...`):
languages as, bn, en, gu, hi, kn, ml, mr, or, pa, ta, te. 24 kHz in 80 ms frames; streaming over HTTP and
WebSocket in its own server; no authentication built in. Needs Linux, Python 3.10-3.12, CUDA 12.8.
GPU memory by the card: 7.7 GB for one seat, 9.7 GB for 8, 15.8 GB for 32.

**Indic Transcribe Core** (`bodhan-ai/indic-transcribe-core`, revision `e083ab7d...`, 17 Sep 2026): 25 languages.
A single pass refuses audio over 45 s; training clips were up to 30 s. Runs on `transformers` (no NeMo needed).
Its card reports an average error of 8.7 on the Voice of India benchmark (Hindi 3.5, Bengali 4.3, Tamil 9.0,
Telugu 11.4) against 10.7 for the hosted Saaras v3 and 17.8 for IndicConformer. The benchmark is run by Josh Talks
with AI4Bharat; its public page did not list this model, so the ranking rests on the card's own table.

**pyannote**: current pipeline `speaker-diarization-community-1` (pyannote.audio 4.x), CC-BY-4.0; the older
`speaker-diarization-3.1` is MIT. Both gated behind accepting terms that share contact details.

**IndicConformer** (`ai4bharat/indic-conformer-600m-multilingual`): MIT, gated, 22 languages without English,
2.55 GB. Its own card now recommends Indic Transcribe instead. Not used.

## Decisions for the user

- Indic Transcribe: get the sign-off, or use it for samples only.
- Big translation model: 12B (lighter, fits an HQ window with Indic Transcribe beside it) or 31B (needs almost
  the whole window to itself). The start script defaults to 12B.
- Maya 2: keep as a Studio HQ candidate or drop; judged by ear and by the QA scores once it can be loaded.
- Speaker similarity threshold: unset (`V1_HQ_SIMILARITY_MIN=0`) until the new model's scale is measured.

## v1.1 WS5: checked again on 25 Nov 2026 (the big translation model, the speaker model)

Read on the models' own pages on 25 Nov 2026. "The page" is the model's Hugging Face page unless said otherwise.
Nothing here was loaded on the GPU.

### Big translation model: 12B first

| | `google/gemma-4-12B-it-qat-w4a16-ct` | `google/gemma-4-31B-it-qat-w4a16-ct` |
|---|---|---|
| The page exists, under the `google` organisation | yes | yes |
| Licence tag on the page | apache-2.0 | apache-2.0 |
| Gated | no gating notice on the page | no gating notice on the page |
| Format | 4-bit weights, 16-bit activations (w4a16), quantization-aware training, compressed-tensors "for native, optimized inference with vLLM" | the same |
| Parameters (the page's safetensors figure) | about 13 B | 33 B (its table says 30.7 B) |
| Files | one `model.safetensors` of 10.3 GB (file list) | not read again (23.3 GB on 23 Nov) |
| Latest commit seen | `1d2c2d7f2466070e69d6fb3fd5ce9a7d75f2f6ee` ("Add response_template to tokenizer_config.json (#9)", "4 months ago") | not read |
| Serving line on the page | none (a Transformers example only); a Google reply in discussion 2 gives `vllm serve google/gemma-4-12B-it-qat-w4a16-ct --max-model-len 32768 --gpu-memory-utilization 0.90` | `vllm serve "google/gemma-4-31B-it-qat-w4a16-ct"` |

**Verified:** the exact ids, the licence tag, that neither page shows a gate, the format, the 12B file size and
commit.

**Not verified:**
- the licence text itself (the pages carry the tag `apache-2.0`, not the text);
- GPU memory: no page gives a figure. The deploy kit gives the 12B server 14 GB and the 31B server 27 GB (weights
  plus room for vLLM's cache). These are our estimates; `smoke.sh big-llm` prints what the server really holds;
- **a vLLM version that starts the 12B checkpoint.** Discussion 2 on its page reports two start failures:
  `'Gemma4UnifiedVisionConfig' object has no attribute 'num_soft_tokens'` (9-11 Jun), which pull request 5 fixed
  in the checkpoint's own `config.json` (merged 12 Jun; it names vLLM issue 45039), and
  `RuntimeError: Shape mismatch: a.size(1) = 4096, size_k = 8192` on a nightly build (12 and 15 Jun). Google asked
  on 6 Aug whether anybody still sees the second; nobody answered. No version is named as working. v0's
  translation server runs vLLM 0.34.0, which is what the kit starts the 12B model with: whether it works is known
  only after the first start. The kit switches image and audio input off (`--limit-mm-per-prompt`), as v0's start
  script does;
- how well either translates Hinglish into Indian languages. That is what `backend/eval/v1/llm_ab.py` is for; its
  rule for "wins" is in the file and in `NEEDS_APPROVAL.md` item 9.

The pages recommend sampling at temperature 1.0, top_p 0.95, top_k 64. Our translation prompts use 0.2-0.3, as
with the small model: that is our choice, not the page's.

**31B on this card:** by the estimates it does not fit. An HQ window leaves about 24 GB free (40 less the voice
engines' 12, separation 1.4, speech-to-text 2.5), and 27 GB plus 4 GB of headroom is 31. It would need the voice
engines stopped too, or a second card.

### QA server's speaker model: `speechbrain/spkrec-ecapa-voxceleb`

| Checked | Result | Where |
|---|---|---|
| Licence | `apache-2.0` | the page's licence tag, and the same field in the model's API record (`cardData.license`) |
| Gated | no (`gated: false`) | API record |
| Version seen | commit `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`, last changed 18 Feb 2025 | API record |
| What it is | ECAPA-TDNN speaker embeddings; trained on VoxCeleb 1 and 2; 16 kHz mono; EER 0.80% on VoxCeleb1-test (cleaned) | the page |
| Commercial use | the page says nothing against it and asks: "Please, cite SpeechBrain if you use it for your research or business." | the page |
| Link | https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb | |

**Verdict:** open to commercial use by its licence. It was already the server's model (since 23 Nov); no switch was
needed. What changed: the server now loads a speaker model only when it is listed in `SPK_LICENCES`
(`qa_server.py`) as checked and open to commercial use. `QA_SPK_MODEL` names another model; ECAPA2
(`Jenthe/ECAPA2`, CC-BY-NC-4.0) and any model nobody checked are refused, the server says why in `/health`, and it
goes on scoring words without a similarity. `QA_SPK_ALLOW_NONCOMMERCIAL=1` lifts that for a measurement that ships
nothing.

**Not verified:** the licence text (tag only), and the standing of the training data: the VoxCeleb page
(robots.ox.ac.uk/~vgg/data/voxceleb) states no licence at all, only a request to cite and a privacy notice. Whether
weights trained on it carry any limit is a legal question this check cannot settle. It is in the decisions list.

**Run on CPU (laptop, Ryzen 7 7435HS, 4 threads, no CUDA device visible, SpeechBrain 1.1.2 with torch 2.15 CPU;
one run, 20 comparisons a row after 2 warm-up calls; a comparison embeds both clips):**

| Pair | Similarity (one pair) | Time per comparison: mean (range) |
|---|---|---|
| the eval reel's speaker, two cuts of 7 s | 0.883 | 765 ms (727-797) |
| the same speaker, two cuts of 3 s | 0.765 | 378 ms (343-440) |
| that speaker against the voice of a made class video, 7 s each | 0.142 | 752 ms (700-831) |
| the same 7 s clip twice | 1.000 | 800 ms (696-952) |

Loading the model took 38.8 s the first time (with its download). The similarities are single pairs of one
speaker: they show the scale has room between "same" and "other", not where a threshold belongs. Not measured: the
Whisper half of the server (not run), the machine's CPU, and the versions the kit installs there (SpeechBrain 1.0.2
with torch 2.5.1; the run above used 1.1.2 because that is what installs on this laptop's Python 3.13).

Found on the way: SpeechBrain's config reader (hyperpyyaml 1.2.3) fails with ruamel.yaml 0.19
(`'Loader' object has no attribute 'max_depth'`); `requirements.qa.txt` now asks for `ruamel.yaml<0.19`.
