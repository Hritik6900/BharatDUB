import type { Metadata } from "next";
import { Anek_Latin, Noto_Sans } from "next/font/google";
import "./globals.css";

const anek = Anek_Latin({ subsets: ["latin"], axes: ["wdth"], variable: "--font-anek" });
const noto = Noto_Sans({ subsets: ["latin"], variable: "--font-noto" });

export const metadata: Metadata = {
  title: "Bharat Dub",
  description: "Dub your videos, or your live stream, into Indian languages in your own voice.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${anek.variable} ${noto.variable} antialiased`}>{children}</body>
    </html>
  );
}
