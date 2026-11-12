import type { Metadata, Viewport } from "next";
import {
  Anek_Bangla,
  Anek_Devanagari,
  Anek_Latin,
  Anek_Tamil,
  Anek_Telugu,
  Noto_Sans,
  Noto_Sans_Bengali,
  Noto_Sans_Devanagari,
  Noto_Sans_Tamil,
  Noto_Sans_Telugu,
} from "next/font/google";
import "./globals.css";

const anek = Anek_Latin({ subsets: ["latin"], axes: ["wdth"], variable: "--font-anek" });
const anekDeva = Anek_Devanagari({ subsets: ["devanagari"], axes: ["wdth"], variable: "--font-anek-deva", preload: false });
const anekTamil = Anek_Tamil({ subsets: ["tamil"], axes: ["wdth"], variable: "--font-anek-tamil", preload: false });
const anekBangla = Anek_Bangla({ subsets: ["bengali"], axes: ["wdth"], variable: "--font-anek-bangla", preload: false });
const anekTelugu = Anek_Telugu({ subsets: ["telugu"], axes: ["wdth"], variable: "--font-anek-telugu", preload: false });
const noto = Noto_Sans({ subsets: ["latin"], variable: "--font-noto" });
const notoDeva = Noto_Sans_Devanagari({ subsets: ["devanagari"], variable: "--font-noto-deva", preload: false });
const notoTamil = Noto_Sans_Tamil({ subsets: ["tamil"], variable: "--font-noto-tamil", preload: false });
const notoBengali = Noto_Sans_Bengali({ subsets: ["bengali"], variable: "--font-noto-bengali", preload: false });
const notoTelugu = Noto_Sans_Telugu({ subsets: ["telugu"], variable: "--font-noto-telugu", preload: false });

const fontVars = [anek, anekDeva, anekTamil, anekBangla, anekTelugu, noto, notoDeva, notoTamil, notoBengali, notoTelugu]
  .map((f) => f.variable)
  .join(" ");

export const metadata: Metadata = {
  title: { default: "Bharat Dub", template: "%s · Bharat Dub" },
  description: "Dub your videos, or your live stream, into Indian languages in your own voice.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#F5F6F8" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${fontVars} min-h-dvh`}>{children}</body>
    </html>
  );
}
