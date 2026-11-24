import { BackendStatus } from "@/widgets/backend-status";

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-8 px-6 py-20">
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">Hinglish Live Transcribe</h1>
        <p className="text-muted-foreground">
          Real-time speech-to-text for Hindi-English code-mixed speech.{" "}
          <span lang="hi">आज की meeting शुरू करते हैं।</span>
        </p>
      </header>
      <BackendStatus />
    </main>
  );
}
