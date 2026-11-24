# EXP-NNN: <title: what was compared, in a few words>

- **Date:** YYYY-MM-DD
- **Status:** planned | partial | done
- **Decision:** ADR-NNNN (link `../adr/NNNN-slug.md`) or "none"

<!--
Rules (delete this block in your copy):
- Every number: source file and section, date, conditions, n (runs, lines, phrases) and spread (range or
  standard deviation), and a label: measured / estimate / target / stand-in.
- Write "(unconfirmed)" for any date or detail that git or a doc does not confirm. Never invent a number.
- Aggregates only: no transcripts, source text, translations, audio, voice samples, video ids, keys or addresses.
- One run proves little: two equal Live runs have differed by about 10 points in timing and 6 in words heard back.
-->

## Question

What we wanted to know, in one or two sentences. Name the target if there is one (for example "within 1 s at
least 90%").

## Hypothesis

What we expected and why, written before the run. If it was not written down beforehand, say so.

## Setup

- Material (for example "the dense 24.9 s reel replayed at real-time speed, 8 loops; not a live person").
- Engine, languages, voice (learned from the stream / recorded / stock), sync mode and hold.
- Where the backend ran (laptop through the tunnel, or the GPU machine).
- Settings compared (flags, values), how many runs each, in what order (interleaved?), tool and command.

## Metrics

Each metric with its definition (for example "first audio = end of the phrase's speech to its first dubbed
audio").

## Results

Label every number. Tables for comparisons, mean (lowest-highest) across runs.

| | setting A | setting B |
|---|---|---|
| Metric 1 | value (range) | value (range) |

## Caveats

What the run does not show: material, run count, what was not measured, anything that went wrong.

## Decision taken

What changed because of it (flag on/off, default, ADR), or "none".

## Links

- Source documents with section names (relative links)
- Commits as short hashes in backticks
- Related EXP and ADR files
