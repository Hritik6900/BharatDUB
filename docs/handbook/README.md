# Bharat Dub handbook

Bharat Dub dubs Hindi and Hinglish video and live streams into other Indian languages and English, in the
speaker's own voice, with captions. This handbook records what is built, why it is built this way, what was tried,
what the numbers are, and how to run it. The v1 documents call the product BharatDb; it is the same product.

State on 25 Nov 2026: v0 (branch `main`, tag `v0-baseline`) runs the product. v1 and v1.1 (branch `v1`) sit beside
it on their own ports, with every new behaviour behind a flag that is off by default. Everything runs on one laptop
and one borrowed A100 GPU machine.

## Start here

| You are | Read in this order |
|---|---|
| **Investor** | [PRODUCT.md](PRODUCT.md) → [PITCH_FACTS.md](PITCH_FACTS.md) → [RESULTS.md](RESULTS.md) → [ROADMAP.md](ROADMAP.md) → [history/TIMELINE.md](history/TIMELINE.md) |
| **New engineer** | [PRODUCT.md](PRODUCT.md) → [ONBOARDING.md](ONBOARDING.md) → [ARCHITECTURE.md](ARCHITECTURE.md) → [RUNBOOK.md](RUNBOOK.md) → [GLOSSARY.md](GLOSSARY.md) → [adr/README.md](adr/README.md) |
| **Founder, six months on** | [history/TIMELINE.md](history/TIMELINE.md) → [adr/README.md](adr/README.md) → [experiments/README.md](experiments/README.md) → [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) → [INCIDENTS.md](INCIDENTS.md) → [../../CHANGELOG.md](../../CHANGELOG.md) |

## Documents

**[PRODUCT.md](PRODUCT.md)**: what Bharat Dub does and for whom. The three modes (Studio for recorded video, Live
for any stream, Streamer for a streamer's own recorded voice), the two engines (Standard, hosted services first;
GPU, our own models first), what is real today and what is only planned.

**[ARCHITECTURE.md](ARCHITECTURE.md)**: the system as it runs, v0 and v1 side by side. Components, ports, data
flow per mode, the provider layer and v1's router, how the GPU machine is laid out, and diagrams. Each section
links the decision behind it.

**[adr/](adr/README.md)**: Architecture Decision Records. One file per decision: the context, the options, what
was chosen, what it cost, and the evidence. Backfilled from the start of the project.

**[experiments/](experiments/README.md)**: one file per experiment: the question, the setup, the numbers with n
and spread, the caveats, and the decision taken.

**[RESULTS.md](RESULTS.md)**: the current scoreboard. Every headline number with its target, date, source and a
label (measured, estimate, target, stand-in), trend tables, and tables generated from the logs.

**[PITCH_FACTS.md](PITCH_FACTS.md)**: only the numbers that are safe to say to an investor, each with its source,
conditions and caveat, and a list of things not to claim.

**[MODELS.md](MODELS.md)**: every model and hosted service: task, where it runs, port, memory, licence, and
whether it is in use, behind a switch, planned or rejected.

**[history/COMMITS.md](history/COMMITS.md)**: every commit on every local branch and tag, generated.
**[history/TIMELINE.md](history/TIMELINE.md)**: the milestones, decisions, results and incidents on one dated line.

**[../../CHANGELOG.md](../../CHANGELOG.md)**: what changed in each version (v0-baseline, v1, v1.1, Unreleased).

**[INCIDENTS.md](INCIDENTS.md)**: postmortems: impact, timeline, root cause, fix and follow-ups.

**[RUNBOOK.md](RUNBOOK.md)**: run v0 and v1, flags, GPU deploy, rollback, the demo-day checklist, what to do when
the GPU machine's address changes. The detailed v1 runbook stays in [../v1/RUNBOOK.md](../v1/RUNBOOK.md).

**[ONBOARDING.md](ONBOARDING.md)**: set up a machine from nothing, the repository layout, the conventions, tests,
evaluation and the documentation rules.

**[SECURITY_AND_CONSENT.md](SECURITY_AND_CONSENT.md)**: consent before any voice is copied, what is kept and for
how long, what is logged and what never is, secrets, and licences to watch.

**[ROADMAP.md](ROADMAP.md)** and **[OPEN_QUESTIONS.md](OPEN_QUESTIONS.md)**: what comes next, what is blocked
and on what, and the decisions still open.

**[GLOSSARY.md](GLOSSARY.md)**: the words used in all of the above (on time, first audio, dur_ratio, words heard
back, hold, HQ, flags, engines, and so on).

## Where the older documents fit

The handbook sums up and links to the documents that were written as the work was done. Those stay the detailed
sources: [SPEC.md](../../SPEC.md) (sections 16-21 are the measured history of v0),
[LIVE_TEST_REPORT.md](../../LIVE_TEST_REPORT.md), [STREAMER_MODE.md](../../STREAMER_MODE.md), and in `docs/v1/`
the [summary](../v1/SUMMARY.md), the [v1.1 summary](../v1/V1_1_SUMMARY.md), the [progress log](../v1/PROGRESS.md),
the [eval report](../v1/EVAL_REPORT.md), the [dense-speech report](../v1/LIVE_DENSE_REPORT.md) and the
[approval checklist](../v1/NEEDS_APPROVAL.md). Where the handbook and a source disagree, the source wins; fix the
handbook.

## Keeping it current

```powershell
powershell -File scripts\docs\gen-docs.ps1          # regenerate commits, indexes and log tables
python scripts\docs\docs-check.py                   # stale tables, or code changed without a CHANGELOG entry
```

The rules (also in [ONBOARDING.md](ONBOARDING.md)): a change in behaviour adds a line under Unreleased in
`CHANGELOG.md`; a design choice gets a new or updated ADR; a measurement gets an EXP file and a line in
`RESULTS.md`; run the generator before each push; commit messages name the ADR or EXP, for example
`router: circuit breaker (ADR-0027)`. Generated parts sit between `<!-- generated:start ... -->` and
`<!-- generated:end ... -->`; text outside them is never touched by the script.
