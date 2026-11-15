# FRONTEND.md — Bharat Dub design system v2

Replaces the first design system (2026-11-13). Owns everything visual in `web/`.
Reference for the feel: sarvam.ai (airy, classic, centred hero, pill buttons, bordered cards). Inspired by, never copied:
the palette, type, orb, layouts and copy here are our own.

## Tokens (`web/app/globals.css`)

- Surfaces: warm paper `--bg`, `--surface` (cards), `--sunken`, hairline `--line`, text `--fg` / `--muted`.
  `.theme-dark` flips all of them; used for `/watch`, the footer and dark panels inside light pages.
- Site theme (`components/layout/ThemeSwitch.tsx`, header button; in the menu sheet on phones): Auto = the three mode pages
  (`/studio`, `/streamer`, `/live`, `<Shell dark>` -> `.theme-page-dark`) are dark and the rest light; Dark / Light = the whole
  site. The choice is `data-theme` on `<html>`, kept in `localStorage` (`bd-theme`) and set before first paint.
- One hue per language: `--hi` saffron, `--ta` teal, `--bn` rose, `--te` violet, `--en` blue. `--spectrum` is the five in a row.
  A hue marks a language (dot, bar, stripe). It never carries text: selected chips are ink-filled, so contrast never depends on a hue.
- Type: Outfit for headings (`.h-display`, weight 500, tight tracking) and for UI and body. Accent words inside headings are
  `<em>`, set in Instrument Serif italic. Geist Mono for `.eyebrow` labels and numbers, Anek (`font-indic`) and Noto for Indic scripts.
  Font variables live on `<html>` so custom CSS can use them.
- Texture: one fixed film-grain layer over the whole site (`body::after`), plus `.tex-grain`, `.tex-dots`, `.tex-hatch`, `.tex-tint`
  (grainy panel washed with the language hues) and `.stage` (dark panel with a hue glow, fading dot grid and grain; set `--glow`).
  `.cells` draws hairline cell grids.
- Shapes: pills for buttons and chips, `.card` (24 px radius, 1 px line), 16 px panels. Utilities: `.card`, `.card-lift`, `.input`,
  `.eyebrow`, `.aura`, `.spectrum`, `.rise`.

## Layout

- `components/layout/Shell.tsx` frames every page: aura, sticky `Header`, content, `Footer`, Lenis.
- `Header`: floating pill nav (transparent at the top, blurred card after scrolling), Products dropdown, mobile sheet, and the
  honest status bar (mock mode / backend down).
- The red "Go live" pill in the header goes to `/streamer` (hidden under 640 px; the menu sheet has it).
- `/streamer` is dark like `/live`: three-step rail, the step's card on the left, and a sticky "Signal path" panel whose orb
  and bars show the real input (recording, chosen device) or a preview of the copied voice while it plays, above the
  service checks (engine times are measured per engine; speech and translation only say that a key is set).
- `Footer`: dark, three promises, link columns, credits, large spectrum wordmark.
- `components/ui/`: `Button`/`LinkButton`, `LanguageChip`, `PageHeader`, `Notice`, `DelayBadge`, `Sparkline`. Icons: lucide-react.

## Voice components (`components/voice/`)

- `VoiceOrb`: CSS orb in the language spectrum. Breathes when idle; swells with loudness from an `analyser` or a `level`.
- `VoiceBars`: canvas bars. With an `analyser` they show real audio (mic on `/live`, `/voices`, landing; dubbed audio on `/watch`).
  Without one they draw a speech-like illustration, used only inside blocks labelled as illustrations.
- `Waveform`: single-stroke waveform for the pipeline story.
- `lib/useMic.ts`: `useMic` (local mic, visuals only, nothing sent) and `useAnalyser` (tap an existing audio node).

## Landing sections (`components/home/`)

Hero (console with hatched rails), ScriptMarquee, Products (three modes: Studio, Streamer, Live; pick one to open its
details, its mock on `.stage` and a "what is happening" step rail that lights one step after the other), Explorer (twelve
capabilities, pick one to light its row), PipelineStory (pinned), Bento (voice profile orbit, live provider status from
`/health`, line-fit stepper, coming-next languages), BeforeAfter toggle, MicTry (mic-driven orb with languages in orbit),
MeasuredNumbers, Trust, FinalCTA.

## Motion

- Lenis on every `Shell` page, driven by the GSAP ticker (`SmoothScroll.tsx`). Inner scroll areas use `data-lenis-prevent`.
- GSAP: hero intro timeline and scroll drift (`Hero.tsx`), pinned scrubbed story (`PipelineStory.tsx`), `[data-reveal]` scroll
  reveals on the landing page (`Reveals.tsx`, mounted last), count-up for measured numbers.
- App pages use the CSS `.rise` entrance only, because their content arrives after fetches.
- `prefers-reduced-motion`: no Lenis, no GSAP, story becomes a plain list, bars draw one static frame.
  `.gs-hide` / `[data-reveal]` hide content only when motion is allowed, with a `<noscript>` fallback.

## Rules that stay

- Never a fake number: delay badges and the measured-numbers block render only from real, non-mock measurements.
- Illustrations are labelled as illustrations. Every AI output carries "AI-dubbed".
- Indic text is never split per character.
- Charts: ink bars with a hue dot and a name label; colour never carries meaning alone.
