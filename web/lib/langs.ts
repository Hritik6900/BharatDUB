export type LangCode = "hi-IN" | "ta-IN" | "bn-IN" | "te-IN" | "en-IN" | "kn-IN" | "ml-IN" | "mr-IN" | "gu-IN" | "pa-IN";

export interface Lang {
  code: LangCode;
  short: string;
  name: string;
  native: string;
  hue: string; // CSS var name with the language colour
}

// The five languages the landing page tells its story with.
export const LANGS: Lang[] = [
  { code: "hi-IN", short: "hi", name: "Hindi", native: "हिन्दी", hue: "var(--hi)" },
  { code: "ta-IN", short: "ta", name: "Tamil", native: "தமிழ்", hue: "var(--ta)" },
  { code: "bn-IN", short: "bn", name: "Bengali", native: "বাংলা", hue: "var(--bn)" },
  { code: "te-IN", short: "te", name: "Telugu", native: "తెలుగు", hue: "var(--te)" },
  { code: "en-IN", short: "en", name: "English", native: "English", hue: "var(--en)" },
];

// Also live in Studio and Live (checked on the real API, 2026-11-13).
export const EXTRA_LANGS: Lang[] = [
  { code: "kn-IN", short: "kn", name: "Kannada", native: "ಕನ್ನಡ", hue: "var(--kn)" },
  { code: "ml-IN", short: "ml", name: "Malayalam", native: "മലയാളം", hue: "var(--ml)" },
  { code: "mr-IN", short: "mr", name: "Marathi", native: "मराठी", hue: "var(--mr)" },
  { code: "gu-IN", short: "gu", name: "Gujarati", native: "ગુજરાતી", hue: "var(--gu)" },
  { code: "pa-IN", short: "pa", name: "Punjabi", native: "ਪੰਜਾਬੀ", hue: "var(--pa)" },
];

const ALL = [...LANGS, ...EXTRA_LANGS];
/** Studio can dub into any of the ten (a non-Hindi video can go to Hindi). */
export const STUDIO_LANGS = ALL;
/** Live assumes a Hindi/Hinglish streamer, so Hindi is not a target there. */
export const TARGET_LANGS = ALL.filter((l) => l.code !== "hi-IN");
/** The four the landing page demos. */
export const SHOWCASE_LANGS = LANGS.filter((l) => l.code !== "hi-IN");

export function lang(code: string): Lang {
  return ALL.find((l) => l.code === code) ?? { code: code as LangCode, short: code, name: code, native: code, hue: "var(--muted)" };
}

/** One line, five scripts: the hero headline. */
export const HEADLINE: Record<string, string> = {
  "hi-IN": "एक आवाज़। हर भाषा।",
  "ta-IN": "ஒரே குரல். எல்லா மொழியும்.",
  "bn-IN": "এক কণ্ঠ। সব ভাষা।",
  "te-IN": "ఒకే గొంతు. ప్రతి భాష.",
  "en-IN": "One voice. Every language.",
};
