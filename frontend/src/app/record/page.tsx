import type { Metadata } from "next";
import Link from "next/link";

import { RecorderPanel } from "@/widgets/recorder-panel";

export const metadata: Metadata = { title: "Record · Hinglish Live Transcribe" };

export default function RecordPage() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-6 py-12">
      <header className="flex items-baseline justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight">Live transcription</h1>
        <Link href="/" className="text-sm text-muted-foreground underline-offset-4 hover:underline">
          Home
        </Link>
      </header>
      <RecorderPanel />
    </main>
  );
}
