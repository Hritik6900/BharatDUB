# ADR-0023: No media/zips/weights/>10 MB in git; no AI-assistant mentions; pre-commit and commit-msg hooks

- **Status:** accepted
- **Date:** 2026-11-23
- **Superseded by:** —

## Context

The work produces large files: model weights (IndicF5 1.4 GB, Gemma 4 12B 10.3 GB, `../../v1/MODELS.md`), stems,
dubbed videos (the pitch video is 35.3 MB for 82 s, `../../v1/PROGRESS.md` v1.1 WS4) and voice samples, which are
also personal data. Local tool files must stay out of the repository. A rule that is only written down gets broken
on a busy day, so v1 enforced it with hooks (`../../v1/ARCHITECTURE.md` rule 13).

## Options considered

| Option | Outcome |
|---|---|
| Rely on `.gitignore` and care | not enough alone: ignore rules do not stop a forced add or a wrong commit message |
| Git LFS for media | not recorded (not evaluated) |
| Ignore rules + `pre-commit` and `commit-msg` hooks for this checkout, never bypassed | **chosen** |

## Decision

- Never commit zips, model weights, media or files over 10 MB. Media and data folders (`data-v1/`, `backend/data`)
  are git-ignored.
- Files, code comments, docs and commit messages name no AI tooling or its vendor. The local rules file
  (git-ignored) and the local tool settings (git-ignored) stay out of git; the ignore rules are written as
  patterns so the ignore file itself does not spell the names (`../../v1/PROGRESS.md` setup).
- `pre-commit` refuses such a commit; `commit-msg` removes such lines from messages. `--no-verify` is forbidden.
  The hooks are installed for the v1 checkout only, so v0's commits are untouched (`../../v1/SUMMARY.md` section 1).
- Keys only in v1's `backend/.env` (git-ignored), never printed (`../../v1/ARCHITECTURE.md` rule 9);
  `backend/.env.example` holds names, no values.

## Consequences

### Good

- Tested with a throwaway file at setup (`../../v1/PROGRESS.md` setup). The 35 MB pitch video stayed in the data
  folder (`../../v1/PROGRESS.md` v1.1 WS4, "Decided").
- Measurement logs in git hold numbers only (ADR-0022).

### Bad

- Hooks live per checkout; a fresh clone has none until they are installed again **(unconfirmed: no install
  script for a new clone is recorded)**.
- Evidence files that matter (recordings, eval audio) live only on the laptop's disk; no backup has run
  (`../../v1/NEEDS_APPROVAL.md` item 15).
- v0's history (before `v0-baseline`) was not covered by these hooks.

## Evidence

- Commits: `92638c1` (setup rules, ignore patterns), `5908ec9`
- Sources: [`ARCHITECTURE.md`](../../v1/ARCHITECTURE.md) rules 9 and 13; [`PROGRESS.md`](../../v1/PROGRESS.md)
  setup, v1.1 WS4; [`SUMMARY.md`](../../v1/SUMMARY.md) section 1; [`.gitignore`](../../../.gitignore)
