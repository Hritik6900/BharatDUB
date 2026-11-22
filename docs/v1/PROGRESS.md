# v1 progress log

One entry per phase: what changed, how to test, how to roll back, measured numbers.

## Setup (Part A), 23 Nov 2026

- Built in a second checkout on the laptop (branch `v1`); v0 runs from `main` in its own folder and was not edited.
- Baseline tag `v0-baseline` checked locally and on the remote: `80c36d8`.
- Commit hooks for this checkout only: a commit that names the assistant or its vendor, carries a zip or a file over
  10 MB is refused; such lines are removed from commit messages. Tested with a throwaway file.
- The ignore rules for the assistant's files are written as patterns, so the ignore file does not spell the names.
- Roll back: delete the `v1` branch checkout; nothing in v0 changed.

## Phase 1: discovery, 23 Nov 2026

- No code changed. `DISCOVERY.md` (map of v0, how each GPU server is called, data, eval, risks) and `PLAN.md`.
- Measured over HTTP only: voice engine 9001 reports 1.43 GB allocated and 82 voices held; Demucs 0.18 GB;
  Whisper 192 ms average decode. Per-process GPU memory needs a shell on the VM: `NEEDS_APPROVAL.md` item 1.
- v0 after this phase: all six GPU servers answer, backend 8010 and website 3000 answer.
