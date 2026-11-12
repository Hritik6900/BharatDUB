# FRONTEND.md — Bharat Dub design system, motion and components

> Prompt/spec. Read together with SPEC.md. This file owns everything visual in `web/`.

## 0. Direction in one paragraph

Bharat Dub turns one voice into every Indian language. The site should feel like **sound becoming script**: a single
voice, drawn as a waveform, that changes colour and alphabet as it crosses languages. Mood reference: the calm,
confident, India-rooted premium feel of Sarvam AI (continuous colour transitions instead of flat blocks, generous
whitespace, wide confident type, cultural grounding without kitsch) and the motion pacing of Dynoz AI.

**Inspired by, never copied.** Take the *mood, pacing, spacing discipline and quality bar* from the references. Do not
use their logos, wordmarks, illustrations, icons, photography, copy, exact gradients, or layouts section-for-section.
Sarvam's identity is a blue-to-orange spectrum with gateway/mandala geometry; ours is **a language-coded colour system
on a living waveform**, which is our own and is about our product. If reference screenshots exist in `design/refs/`,
study them for rhythm and polish only.

## 1. Tokens

### Colour — every hue means a language

| Token | Hex | Meaning |
|---|---|---|
| `--ink` | `#14161F` | Text, primary buttons |
| `--porcelain` | `#F5F6F8` | Page background (cool, not cream) |
| `--mist` | `#E4E7EE` | Hairlines, inputs, quiet surfaces |
| `--slate` | `#5D6475` | Secondary text |
| `--hi` (Hindi, source) | `#F2A33A` | Marigold — the original voice |
| `--ta` (Tamil) | `#0E8F8A` | Peacock teal |
| `--bn` (Bengali) | `#D2344A` | Alta red |
| `--te` (Telugu) | `#7A4FD1` | Jamun violet |
| `--en` (English) | `#3A5BD9` | Indigo |

Rules:
- Language colours appear **only** where that language is: waveform segments, language chips, caption underlines,
  the active track in the player. Never as decoration.
- The one gradient in the system is the **voice ribbon**: a horizontal blend from `--hi` into the selected target
  language, used on the hero waveform and the player progress bar. It means "this voice is being dubbed".
- Dark mode (`/live`, `/watch` default to dark because they sit next to a video): `--ink-d #0E1016` background,
  `--porcelain-d #ECEEF3` text, same language hues raised 8% in lightness. Provide both via `prefers-color-scheme`
  plus a toggle.
- Contrast: all text ≥ 4.5:1. Language hues are never used for body text on porcelain.

### Type

| Role | Family | Notes |
|---|---|---|
| Display + UI | **Anek** (Google Fonts: Anek Latin, Anek Devanagari, Anek Tamil, Anek Bangla, Anek Telugu) | One family across five scripts, variable **width** and weight. The width axis is our signature: it breathes with audio amplitude in the hero. |
| Body + long text | **Noto Sans** + Noto Sans Devanagari / Tamil / Bengali / Telugu | Reliable coverage for captions and transcripts |
| Numbers in stats | Anek Latin with `font-variant-numeric: tabular-nums` | No monospace labels |

Scale (rem, 1.25 ratio): 0.8 / 1 / 1.25 / 1.563 / 1.953 / 2.441 / 3.815 (hero only, `clamp(2.6rem, 7vw, 5.4rem)`).
Body 1rem / 1.6. Line length ≤ 72ch. Sentence case everywhere. No all-caps labels, no eyebrow text above headings,
no single highlighted word in headlines.

### Shape, space, elevation

- Radius has hierarchy: 999px for chips and the record button, 20px for media frames, 12px for inputs and panels,
  0 for full-bleed sections.
- Spacing on an 8px grid; section padding `clamp(80px, 12vh, 160px)`.
- No drop shadows on cards. Depth comes from a 1px `--mist` border and, for the floating player only, a soft
  `0 20px 60px -30px rgba(20,22,31,.35)`.

## 2. Motion system: GSAP + Lenis

### Setup (Next.js App Router)

```
npm i gsap @gsap/react lenis
```

`web/components/motion/SmoothScroll.tsx` (client component, marketing routes only):

```tsx
'use client';
import { useEffect } from 'react';
import Lenis from 'lenis';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
gsap.registerPlugin(ScrollTrigger);

export default function SmoothScroll({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const lenis = new Lenis({ lerp: 0.1, smoothWheel: true });
    lenis.on('scroll', ScrollTrigger.update);
    const tick = (t: number) => lenis.raf(t * 1000);
    gsap.ticker.add(tick);
    gsap.ticker.lagSmoothing(0);
    return () => { gsap.ticker.remove(tick); lenis.destroy(); };
  }, []);
  return <>{children}</>;
}
```

- Use `useGSAP` from `@gsap/react` in every animated component (scoped, auto-cleanup).
- Lenis runs on `/` (landing) only. App pages (`/studio`, `/live`, `/watch`, `/dashboard`) use native scroll.
- `prefers-reduced-motion`: no Lenis, no scroll-scrubbed timelines, no width breathing; show final states, keep
  instant feedback (button presses, progress).

### Motion principles

1. **One orchestrated moment per page.** On the landing it is the hero voice morph. Everything else is quiet.
2. **Motion explains the product.** The only scroll-pinned sequence is the pipeline story, because the pipeline is a
   real sequence (listen → understand → translate → speak).
3. No fade-up-on-every-section, no hover lift on every card, no parallax for its own sake.
4. Easing: `power3.out` for entrances (0.6–0.9s), `expo.inOut` for the morph (1.2s), `none` for scrubbed timelines.
5. App UI motion is functional only: progress, state changes, audio-reactive meters.

## 3. Landing page `/` — sections and components

### 3.1 `HeroVoiceMorph` (the memorable thing)

- Full-viewport, porcelain. Left-aligned headline, max 12 words, e.g. **"Ek awaaz. Har bhasha."** set huge in Anek.
- Under it, the **voice ribbon**: a single-line SVG waveform across the width.
- On load (once): the headline types in Devanagari, then the whole line **morphs script-by-script** — Hindi →
  Tamil → Bengali → English — each step: characters split (GSAP SplitText), old glyphs collapse in width
  (Anek `wdth` 125 → 50) while the new script expands (50 → 100), ribbon segment colour shifts to that language.
  Total ≤ 4.5s, then rests on the visitor's browser language if it is one we support.
- A round **Play** button: plays a real 6-second clip (our own voice, consented) in Hindi then the Tamil dub;
  the ribbon and the headline's `wdth` axis follow live amplitude via Web Audio `AnalyserNode` (clamp 70–115).
- Secondary line (body size): "Dub your videos, or your live stream, into Indian languages in your own voice."
- Two buttons: "Dub a video" (→ `/studio`), "Go live" (→ `/live`).

### 3.2 `LanguageRail`

A horizontal strip of the supported languages, each a chip in its own hue with its name in its own script.
Hover/focus plays a 1.5s sample of the same sentence in that language. Static otherwise.

### 3.3 `PipelineStory` (scroll-pinned, the only one)

Pinned for ~300vh, `scrub: true`. One sentence travels through four numbered stages (numbers are correct here — it is
a sequence):
1. **Listen** — raw waveform with background noise; noise layer fades out (vocal separation).
2. **Understand** — waveform splits into word boxes with Hinglish transcript.
3. **Translate** — words re-order and change script into Tamil (word-order change is the point: show it).
4. **Speak** — a new waveform in teal, same rhythm, labelled "your voice, in Tamil".
A thin progress line on the left shows which stage you are in. Text for each stage ≤ 2 lines.

### 3.4 `TwoModes`

Two large media frames side by side (stacked on mobile), not cards:
- **Studio**: an A/B player on a real reel. One toggle switches Original / Tamil / Bengali; the ribbon colour follows.
- **Live**: a looping 12s screen capture of `/watch` with captions changing language and the delay badge
  ("Dub delay 3.6 s" — from a real measured run; never invent it).

### 3.5 `MeasuredNumbers`

Three numbers maximum, pulled from `/api/dashboard` or `eval/results.csv` at build time: e.g. Studio turnaround,
Live median delay, languages supported. Numbers count up once when in view (0.8s). If a number is not measured yet,
the block is hidden — never placeholder numbers.

### 3.6 `Consent` strip

One quiet line plus link: "Your voice is cloned only with your recorded consent, and you can delete it any time."

### 3.7 `Footer`

Product links, "AI-dubbed content is labelled", credits to open-source tools, Gnani AI models credit.

## 4. App pages (quiet, functional)

### `/studio`
- Drop zone (20px radius, dashed `--mist` border; on drag-over the border becomes the voice ribbon).
- Language chips (multi-select, language hues), voice choice (My voice / Stock voice), required ownership checkbox.
- Primary button "Start dubbing".

### `/studio/[jobId]`
- Vertical stage list (numbered: real sequence) with live timings via SSE; the active stage shows a small
  amplitude-style progress bar in the source hue.
- When done: **A/B player** (the hero component of the app), language tabs coloured by hue, captions under video.
- Review table: source | translation | ▶ | edit. Editing a line shows "Re-rendering this line…" inline, then
  "Updated" — same word in the toast.
- Downloads: "Download Tamil video", "Download Tamil subtitles".

### `/live` (dark)
- Session form → big "Go live" button. Then: live transcript column, per-language caption columns (hue underline),
  latency sparkline (last 60 chunks), translated chat feed, "Copy viewer link".

### `/watch/[id]` (dark, mobile-first)
- Video on top (16:9, 20px radius), language switcher as large chips below, captions in the chosen script,
  delay badge, chat input. `?demo=1` shows all languages' captions side by side, larger.

### `/voices`
- Record button (round, pulses with mic level), the consent sentence to read aloud displayed large, waveform
  preview, "Save voice" and "Delete voice".

### `/dashboard`
- Minutes dubbed, languages used, Studio median turnaround, Live p50/p95. Charts in language hues only where the
  series is a language; otherwise ink/slate.

## 5. Component inventory (`web/components/`)

| Component | Notes |
|---|---|
| `motion/SmoothScroll` | Lenis + GSAP ticker bridge (above) |
| `motion/useReducedMotion` | hook used by every animated component |
| `voice/Waveform` | SVG path from amplitude array; props: `samples`, `hue`, `toHue`, `live` |
| `voice/AudioReactive` | Web Audio AnalyserNode → normalized amplitude stream (rAF) |
| `hero/HeroVoiceMorph` | SplitText + Anek `wdth` axis morph, play clip |
| `hero/LanguageRail` | chips with sample playback |
| `story/PipelineStory` | pinned ScrollTrigger timeline, 4 stages |
| `player/ABPlayer` | one video element, swaps audio tracks / sources, keeps currentTime |
| `player/LivePlayer` | WebSocket PCM scheduler, jitter buffer, sync offset slider |
| `ui/LanguageChip`, `ui/Button`, `ui/Toggle`, `ui/DropZone`, `ui/StageList`, `ui/DelayBadge`, `ui/Sparkline` | |
| `layout/Nav`, `layout/Footer` | Nav: wordmark "Bharat Dub" set in Anek wide, links Studio · Live · Voices · Dashboard |

Our wordmark: "Bharat Dub" in Anek Latin, width 112, weight 600, with a short marigold-to-teal ribbon under "Dub".
No monogram copied from anyone.

## 6. Tailwind config (excerpt)

```ts
theme: {
  extend: {
    colors: {
      ink: '#14161F', porcelain: '#F5F6F8', mist: '#E4E7EE', slate: '#5D6475',
      lang: { hi: '#F2A33A', ta: '#0E8F8A', bn: '#D2344A', te: '#7A4FD1', en: '#3A5BD9' },
    },
    fontFamily: {
      display: ['var(--font-anek)', 'Noto Sans', 'sans-serif'],
      body: ['var(--font-noto)', 'Noto Sans Devanagari', 'Noto Sans Tamil', 'Noto Sans Bengali', 'Noto Sans Telugu', 'sans-serif'],
    },
    borderRadius: { chip: '999px', media: '20px', panel: '12px' },
  },
}
```
Load fonts with `next/font/google` (Anek variable with `wdth` axis, Noto subsets per script).
(If the project uses Tailwind v4, express the same tokens with `@theme` in `app/globals.css`.)

## 7. Quality floor (acceptance checklist)

- [ ] Lighthouse: Performance ≥ 90 on `/` (mobile), Accessibility ≥ 95.
- [ ] Hero morph runs once, ≤ 4.5s, can be skipped by scrolling; no layout shift (reserve hero height).
- [ ] `prefers-reduced-motion` fully respected (no Lenis, no scrub, static final states).
- [ ] Keyboard: every control reachable, visible focus ring (2px `--ink` offset 2px; on dark, `--porcelain-d`).
- [ ] All scripts render with correct fonts (test Hindi, Tamil, Bengali, Telugu, English strings).
- [ ] Responsive from 360px; `/watch` is perfect on a phone.
- [ ] No placeholder or invented numbers anywhere.
- [ ] No asset, logo, copy or illustration taken from Sarvam AI, Dynoz AI or anyone else.
- [ ] Screenshot `/`, `/studio/[jobId]`, `/watch/[id]` at 390px and 1440px and review them before calling it done.

## 8. Prompt

> Read SPEC.md and FRONTEND.md. Build the design system first: fonts, tokens, Tailwind config, `SmoothScroll`,
> `useReducedMotion`, `Waveform`, `AudioReactive`, `LanguageChip`, `Button`. Then build the landing page `/` with
> `HeroVoiceMorph`, `LanguageRail`, `PipelineStory`, `TwoModes`, `MeasuredNumbers` (hidden until real data), `Consent`,
> `Footer`. Use GSAP (with @gsap/react and SplitText) and Lenis exactly as in section 2. Take screenshots at 390px and
> 1440px, critique them against section 7, fix, then stop and show me before moving to the app pages.
