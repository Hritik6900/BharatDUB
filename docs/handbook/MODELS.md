# Models

Every model Bharat Dub uses, switched off, plans to use or rejected. Dated 2026-11-25; the licences of Demucs,
Silero VAD and IndicF5 were read on their official pages on 2026-11-26 (section "Licences read on 26 Nov 2026").
The detailed source, with what was checked on each model's own page and when, is [`../v1/MODELS.md`](../v1/MODELS.md)
(checked 23 Nov 2026, again for two models on 25 Nov 2026). Other sources: SPEC sections 6, 16, 17 and 21,
`docs/v1/DISCOVERY.md`, v0's `gpu_engine/README.md`.

Licence notes are what the model pages or our documents state. "Commercial OK?" is not legal advice; open items
are in [SECURITY_AND_CONSENT.md](SECURITY_AND_CONSENT.md#5-licences-to-watch) and
[OPEN_QUESTIONS.md](OPEN_QUESTIONS.md).

**Versions.** No self-hosted model is pinned to a revision: the deploy kit and compose files use `main`
(`docs/v1/NEEDS_APPROVAL.md` item 12). Hashes below are what was seen on the pages, not what runs.

## In use

| Model | Version | Task | Where | Port | GPU memory | Licence | Commercial OK? | Status |
|---|---|---|---|---|---|---|---|---|
| Gnani Prisma v3 (`prisma-v3.0`) | hosted | speech-to-text, REST (Studio) and realtime with partials (Live) | hosted | - | - | vendor terms (not reviewed here; unconfirmed) | paid account | in use; first hearing in both engines (ADR-0016) |
| Gnani Timbre v2.5 (`timbre-v2.5`) | hosted | stock voices, English, fallback voice | hosted | - | - | vendor terms (unconfirmed) | paid account | in use |
| Gnani `vachana-vc-v1` | hosted | copied voice from a 768-dim embedding (hosted clone) | hosted | - | - | vendor terms (unconfirmed) | paid account | in use: Studio copied voice when no GPU voice, English copy in Live |
| Gemini 3.5 Flash (`gemini-3.5-flash`) | hosted | translation (Studio, main model), redo of wrong-script Live replies | hosted, OpenAI-compatible endpoint | - | - | vendor terms (unconfirmed) | paid key | in use |
| Gemini 3.1 Flash-Lite (`gemini-3.1-flash-lite`) | hosted | Live translation, Standard engine | hosted | - | - | vendor terms (unconfirmed) | paid key | in use: 0.82 s a phrase, 0 of 48 replies in a wrong script (SPEC 16, 14 Nov 2026, **measured**) |
| IndicF5 (`ai4bharat/IndicF5`) + Vocos vocoder | not pinned; page commit `fb652a96` (first characters only) | copied voice, 11 Indian languages, no English | VM, 3 processes under CUDA MPS | 9001-9003 | about 12 GB for three (**estimate**); 1.43 GB torch allocation each (**measured**, 23 Nov) | MIT tag on its card, gated (auto); a model fine-tuned from it claims a non-commercial lineage (below) | **legal confirmation needed** (26 Nov 2026; [OPEN_QUESTIONS](OPEN_QUESTIONS.md) question 21, NEEDS_APPROVAL item 28) | in use; DiT 337.1 M + Vocos 13.6 M parameters (SPEC 17) |
| Whisper-Hindi2Hinglish-Apex (Oriserve) | not pinned | Live speech-to-text with partials, Hindi/Hinglish only, Latin letters | VM, CTranslate2 float16 | 9030 | about 2-2.5 GB (**estimate**) | Apache-2.0 | yes | in use behind Prisma in the GPU engine |
| Gemma 4 E4B (`google/gemma-4-E4B-it`) on vLLM 0.34.0 | not pinned | translation, GPU engine | VM, bf16, context 4096 | 9020 | about 18-19 GB (memory share 0.45-0.5, **estimate**) | Apache-2.0 (confirmed on card, `../v1/MODELS.md`) | yes | in use; 0.17 s a translation with the backend on the VM (SPEC 21, **measured**) |
| Demucs `htdemucs` | not pinned | separation of voice and background (Studio, voice recordings) | VM (GPU) else laptop CPU | 9010 | about 1.4 GB (**estimate**) | code MIT (both repositories, 26 Nov 2026); **weights: "not clear"** by the maintained repository's own README (below) | code yes; weights unsettled (question 13) | in use; 60 s of audio in 4.0-4.8 s through the tunnel vs 38.9-40.3 s on CPU (SPEC 16/17, **measured**) |
| Silero VAD | not pinned (`silero-vad` 6.2.3 installed on the laptop) | speech detection, Studio segmentation; engine VAD | laptop CPU; VM CPU | - | - | MIT (licence file, 26 Nov 2026) | yes by its licence | in use |
| speechbrain ECAPA-TDNN (`speechbrain/spkrec-ecapa-voxceleb`) | page commit `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286` | speaker similarity for QA | QA server, CPU | 9045 | 0 (CPU) | Apache-2.0 | yes by its licence; training data (VoxCeleb) states no licence | in use for measurement on the laptop CPU; server not deployed (item 4). 765 ms a comparison of two 7 s clips (727-797, 20 runs, 25 Nov, **measured**) |

## Switch (built, off by default)

| Model | Version | Task | Where | Port | GPU memory | Licence | Commercial OK? | Why it is a switch |
|---|---|---|---|---|---|---|---|---|
| Indic-Mio (`SPRINGLab/Indic-Mio`) + MioCodec | not pinned | second voice, 0.6 B, no sample text needed, speaks English | VM | 9040 (model on 9021) | all engines with it about 39 of 40 GB (**measured**, SPEC 21) | Apache-2.0 (v0 `mio_engine.py` header) | yes | stopped. Timing on a voice learned from a fast stream: within 1 s 87% -> 50% (SPEC 21, one run). A second voice between lines was heard on a real stream; short lines stay on IndicF5 (ADR-0017) |

## Planned (code written, model not loaded)

| Model | Version | Task | Port | GPU memory (source) | Licence | Commercial OK? | Waits on |
|---|---|---|---|---|---|---|---|
| IndicF5, one batching process | as above | replace three processes for v1 | 9041 | about 4 GB (**estimate**) | as above | as above: legal confirmation needed | item 10 |
| Maya 2 Native (`maya-research/maya2-native`, 2.5 B) | card revision `87a83efd` (first characters) | candidate voice in Studio HQ, English in a copied voice | 9042 | 7.7 GB steady, 9.2 GB loading (card's figure) | Apache-2.0, not gated | yes | item 8 (HQ window, A/B by ear) |
| Indic Transcribe Core (`bodhan-ai/indic-transcribe-core`, 1.2 B) | revision `e083ab7d` (first characters) | second hearing for Studio HQ, 25 languages | 9043 | 9.2 GiB at batch 8 (card) | Indic Open Model License v1.0, gated | self-hosting yes; a hosted service others call needs the authors' written sign-off | item 11 + licence decision |
| Gemma 4 12B 4-bit (`google/gemma-4-12B-it-qat-w4a16-ct`) | page commit `1d2c2d7f2466070e69d6fb3fd5ce9a7d75f2f6ee` | Studio HQ translation and review | 9044 | 14 GB given by the kit (**estimate**; weights 10.3 GB) | Apache-2.0 tag | yes by tag | item 9; whether vLLM 0.34.0 starts it is unknown |
| Gemma 4 31B 4-bit (`google/gemma-4-31B-it-qat-w4a16-ct`) | not read | as 12B, only if 12B wins | 9044 | 27 GB given by the kit (**estimate**; weights 23.3 GB) | Apache-2.0 tag | yes by tag | does not fit beside the voice engines by the estimates |
| Whisper large-v3-turbo via faster-whisper | not pinned | hear a dubbed line back in any of our languages (QA, second judge) | 9045 (CPU) | 0 | MIT | yes | item 4 |
| pyannote `speaker-diarization-community-1` | not pinned | who speaks when (Studio HQ) | 9045 (CPU) | not stated | CC-BY-4.0, gated (terms share contact details) | yes, with attribution | item 7 |

## Rejected or not used

| Model | Why | Source |
|---|---|---|
| ECAPA2 (`Jenthe/ECAPA2`) | CC-BY-NC-4.0, non-commercial. Earlier similarity numbers (0.63-0.76 copied voice, 0.86-0.89 real person, 21 Nov) used it and do not carry over to the new scale. The QA server refuses it | `../v1/MODELS.md` finding 1; ADR-0025 |
| Whisper large-v3-turbo / large-v3 for Live speech-to-text | not better on the hard set: key words clean / hard: Apex 69 / 48, turbo 67 / 40, large-v3 65 / 50 at about four times the decode time (388 ms vs 87 ms). Turbo is still planned for QA | SPEC 21, 21 Nov 2026, **measured**, one run |
| Gemini 3.5 Flash-Lite for Live | 1.06 s a phrase and 4 of 48 replies in a wrong script | SPEC 16, 14 Nov 2026, **measured** |
| Gemini 3.7 Flash for Live | 1.84 s a phrase | SPEC 16, **measured** |
| Hosted clone for Live with dense speech | 5 of 21 phrases in the copied voice, delay grew to 14.5 s; IndicF5: 31 of 32 | SPEC 16, 14 Nov 2026, **measured** |
| IndicConformer (`ai4bharat/indic-conformer-600m-multilingual`) | its own card recommends Indic Transcribe | `../v1/MODELS.md` |
| MelBand RoFormer vocals model | no speech-against-music comparison found, licence unsettled | `../v1/MODELS.md` finding 7 |
| SraVaani-0.5-live, Gemma 3 | gated, our login had no access; not tried | v0 `gpu_engine/README.md` |
| Prefix caching / speculative translation (not models, but model-call features) | no measured gain; removed in WS6 | ADR-0029 |

## Licences read on 26 Nov 2026

Each page was fetched on 26 Nov 2026 and is quoted as it stood. The full record, with what could not be fetched, is
in [`../v1/MODELS.md`](../v1/MODELS.md), "Checked on 26 Nov 2026". Nothing here is legal advice.

| Name | Licence, as the page says | Link | Date read |
|---|---|---|---|
| Demucs, code (original repository, archived) | MIT ("MIT License, Copyright (c) Meta Platforms, Inc. and affiliates."); README: "Demucs is released under the MIT license as found in the LICENSE file." and "this repository is not maintained anymore" | https://github.com/facebookresearch/demucs/blob/main/LICENSE | 2026-11-26 |
| Demucs, code and weights (the fork its author names "the officially maintained Demucs") | code MIT (the same licence file). Weights, README: "The license of the weights is not clear: MusDB contains some data that were only usable for research purpose." | https://github.com/adefossez/demucs (LICENSE; README, "License") | 2026-11-26 |
| Silero VAD | MIT ("MIT License, Copyright (c) 2020-present Silero Team"); README: "Published under permissive license (MIT) Silero VAD has zero strings attached" | https://github.com/snakers4/silero-vad/blob/master/LICENSE | 2026-11-26 |
| IndicF5 (`ai4bharat/IndicF5`), its own card | `license: mit` (record of the model, revision `fb652a96e508091045890dae5bb99fe511facbcf`), gated; says nothing about commercial use | https://huggingface.co/ai4bharat/IndicF5 | 2026-11-26 |
| IndicF5 as described by a model fine-tuned from it (`dheeyantra/dhee-indic-f5`, CC-BY-NC-4.0) | "inherits non-commercial terms from its lineage: it is fine-tuned from `ai4bharat/IndicF5`, which builds on **F5-TTS** (trained on the **Emilia** dataset, CC-BY-NC-4.0) and **IIT-Madras Indic TTS** data (non-commercial)" | https://huggingface.co/dheeyantra/dhee-indic-f5 | 2026-11-26 |
| F5-TTS (`SWivid/F5-TTS`), the model IndicF5 thanks and builds on | code MIT; "The pre-trained models are licensed under the CC-BY-NC license due to the training data Emilia" (card tag `cc-by-nc-4.0`) | https://github.com/SWivid/F5-TTS ; https://huggingface.co/SWivid/F5-TTS | 2026-11-26 |

**IndicF5: legal confirmation needed.** The two rows disagree, and no page of AI4Bharat says whether IndicF5's
weights began from F5-TTS's pre-trained weights. Until AI4Bharat confirms commercial use in writing, or a lawyer
has read the lineage, do not say IndicF5 is cleared for commercial use
([OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) question 21; `../v1/NEEDS_APPROVAL.md` item 28).

**Demucs:** the MIT licence covers the code. The weights we use (`htdemucs`) are the ones its maintainer calls "not
clear" ([OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) question 13).

Decided in [ADR-0010](adr/0010-indicf5-own-gpu-voice.md), [ADR-0015](adr/0015-gpu-stt-translation.md),
[ADR-0016](adr/0016-hosted-stt-first.md), [ADR-0017](adr/0017-one-voice-short-lines.md),
[ADR-0025](adr/0025-speaker-model-licence.md), [ADR-0026](adr/0026-gated-models.md).
