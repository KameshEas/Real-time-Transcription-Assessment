import type { Metadata } from "next";
import { Geist, Geist_Mono, Noto_Sans_Devanagari } from "next/font/google";

import { Providers } from "./providers";
import "./globals.css";

const geistSans = Geist({ variable: "--font-latin", subsets: ["latin"] });
const devanagari = Noto_Sans_Devanagari({ variable: "--font-deva", subsets: ["devanagari"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Hinglish Live Transcribe",
  description: "Real-time speech-to-text for Hindi-English code-mixed speech",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${devanagari.variable} ${geistMono.variable} h-full antialiased`}
      style={{ "--font-sans": "var(--font-latin), var(--font-deva), sans-serif" } as React.CSSProperties}
    >
      <body className="min-h-full flex flex-col">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
