import type { Metadata, Viewport } from "next";
import {
  Anek_Bangla,
  Anek_Devanagari,
  Anek_Tamil,
  Anek_Telugu,
  Geist,
  Geist_Mono,
  Instrument_Serif,
  Noto_Sans_Bengali,
  Noto_Sans_Devanagari,
  Noto_Sans_Tamil,
  Noto_Sans_Telugu,
} from "next/font/google";
import "./globals.css";

const serif = Instrument_Serif({ subsets: ["latin"], weight: "400", style: ["normal", "italic"], variable: "--font-serif" });
const geist = Geist({ subsets: ["latin"], variable: "--font-geist" });
const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono" });
const anekDeva = Anek_Devanagari({ subsets: ["devanagari"], variable: "--font-anek-deva", preload: false });
const anekTamil = Anek_Tamil({ subsets: ["tamil"], variable: "--font-anek-tamil", preload: false });
const anekBangla = Anek_Bangla({ subsets: ["bengali"], variable: "--font-anek-bangla", preload: false });
const anekTelugu = Anek_Telugu({ subsets: ["telugu"], variable: "--font-anek-telugu", preload: false });
const notoDeva = Noto_Sans_Devanagari({ subsets: ["devanagari"], variable: "--font-noto-deva", preload: false });
const notoTamil = Noto_Sans_Tamil({ subsets: ["tamil"], variable: "--font-noto-tamil", preload: false });
const notoBengali = Noto_Sans_Bengali({ subsets: ["bengali"], variable: "--font-noto-bengali", preload: false });
const notoTelugu = Noto_Sans_Telugu({ subsets: ["telugu"], variable: "--font-noto-telugu", preload: false });

const fontVars = [serif, geist, geistMono, anekDeva, anekTamil, anekBangla, anekTelugu, notoDeva, notoTamil, notoBengali, notoTelugu]
  .map((f) => f.variable)
  .join(" ");

export const metadata: Metadata = {
  title: { default: "Bharat Dub: one voice, every Indian language", template: "%s · Bharat Dub" },
  description: "Dub your videos, or your live stream, into Indian languages in your own voice.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#faf8f4" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={fontVars}>
      <body className="min-h-dvh">
        <noscript>
          <style>{".gs-hide,[data-reveal]{visibility:visible!important}"}</style>
        </noscript>
        {children}
      </body>
    </html>
  );
}
