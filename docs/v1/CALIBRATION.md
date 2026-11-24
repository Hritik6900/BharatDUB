# Calibrating the heard-back judge

Studio HQ scores every take of a dubbed line: a speech-to-text (the "judge") hears the take, and the score is the
share of the line's words that came back. A line whose kept take is under the flag line (`V1_HQ_BACKCHECK_MIN`,
0.9) is flagged for a person to hear. Whether 0.9 is the right line, and how often the judge is right at all, can
only be said by comparing it with a person's ear. The calibration page does that.

**State on 25 Nov 2026: no labels yet.** Nobody has labelled a line, so there is no agreement figure and no
recommended flag line. 0.9 is the value v1 started with, not a measured one. This file says how to get both.

## Switch it on

In v1's `backend/.env`, then restart the backend:

```
V1_HQ_CALIBRATE=true
V1_HQ_JUDGE=true        # recommended with it: takes are scored by the corrected rule and store what was heard
```

Open `http://localhost:3100/studio/calibrate` (also in the footer: "Check the checker"). With the flag off the
page says that it is switched off and the routes answer 404.

There must be something to label: takes of HQ jobs whose audio is still in the cache. Jobs run before v1.1 did not
store what the judge heard; once, from `backend/`, run

```
python -m eval.v1.rescore --data ..\data-v1 --jobs <job ids> --out ..\data-v1\eval\ws3\rescore --write-hearings
```

which reads those hearings from the cache (no voice is made, nothing is heard again) and writes them to
`<DATA_DIR>/calibration/hearings.json`, so that old takes are scored by the rule in use like new ones.

## Use it

1. The page plays one take and shows the words it should say and the language. It does not show the score, which
   take of the line it is, or whether it was the one kept.
2. Answer **Good** (every word is clear and right), **Bad** (a word is wrong, missing or unclear), or **Skip**
   (you cannot judge it: not your language, a line cut off). Keys: `g`, `b`, `s`. "Undo my last answer" takes the
   last label back.
3. Label in a language you speak. The language box limits the queue to one language.
4. The queue takes turns between takes with low, middle, high and full scores, so that a short session already
   covers the range; inside the ten takes handed out the order tells nothing about the score.

Thirty labels with at least five good and five bad ones are needed before a flag line is recommended
(`V1_HQ_CALIBRATE_MIN_LABELS`). More is better: with thirty labels one answer moves the agreement by 3 points.

## What the page shows

- **Agreement with the flag line in use**: of the labelled takes, the share where the judge and you say the same
  (flagged and you said bad, or not flagged and you said good), and the four counts behind it:
  flagged and bad, flagged but good (a false alarm), not flagged but bad (a miss), not flagged and good.
- **Recommended flag line**: see below. With no labels the page says "No labels yet"; with too few it says how
  many there are and how many are needed. It never shows a number it could not work out.
- **By language**: the same agreement per language, when more than one has labels.

## How the recommendation is computed

For the labelled takes there is a list of pairs (score, good or bad). Every value half-way between two
neighbouring scores is tried as the flag line `t`; a take with a score under `t` counts as flagged. For each `t`:

```
caught  = bad takes that are flagged      / all bad takes
cleared = good takes that are not flagged / all good takes
balanced accuracy = (caught + cleared) / 2
```

The `t` with the highest balanced accuracy is recommended; of equal ones, the one nearest the flag line in use.
Balanced accuracy is used rather than plain agreement because most takes are good: a judge that never flags
anything would agree with you most of the time and still be useless.

The recommendation is only that. To use it, set `V1_HQ_BACKCHECK_MIN=<value>` (and, with adaptive takes,
`V1_HQ_ADAPTIVE_MIN` if more takes should be made up to another line) and restart the backend.

What the number cannot tell you: if the best `t` still leaves many misses and false alarms, the judge itself is
the problem for that language, not the line. The per-language table shows where. The judge for a language is set
with `V1_HQ_JUDGE_ORDER` / `V1_HQ_JUDGE_BY_LANG` (`RUNBOOK.md`).

## Where the labels are

`<DATA_DIR>/calibration/labels.jsonl` (for v1 on the laptop: `data-v1\calibration\`), one line per answer: the
time, the take, good or bad, and the take's language, score, judge and rule at that moment. The folder is in the
data folder, which is never committed; nothing of it goes to `logs/`. Deleting the file starts over.

A label stays valid as long as the rule that produced the take's score is the rule in use. Labels on takes
scored by another rule are counted separately ("left out") and not mixed into the agreement.

## Routes

| Route | What |
|---|---|
| `GET /api/v1/calibrate/next?n=10&lang=` | up to `n` unlabelled takes: `id`, `lang`, `text`. Never a score |
| `GET /api/v1/calibrate/audio/{id}` | the take's audio |
| `POST /api/v1/calibrate/labels` `{id, label}` | `good`, `bad` or `undo` |
| `GET /api/v1/calibrate/summary` | counts, agreement at the flag line in use, the recommendation or why there is none |
