"use client";

import { useMachine } from "@xstate/react";
import { Mic, Square, RotateCcw, Loader2 } from "lucide-react";
import { useEffect, useMemo, useRef } from "react";

import { segmentLang } from "@/entities/segment";
import { formatClock, recorderMachine, ScriptPicker, useElapsed, type RecorderContext } from "@/features/record-session";
import { useReadiness } from "@/shared/api/health";
import { WS_URL } from "@/shared/config/env";
import { Button } from "@/shared/ui/button";
import { LevelMeter } from "@/shared/ui/level-meter";

const DONE_TEXT: Record<NonNullable<RecorderContext["doneReason"]>, string> = {
  stopped: "Recording finished.",
  limit: "Stopped at the session time limit.",
  idle: "Stopped because no audio arrived for a while.",
  engine_closed: "The transcription service ended the session.",
  error: "The transcription service hit an error and ended the session.",
};

export function RecorderPanel() {
  const [state, send] = useMachine(recorderMachine, { input: { url: `${WS_URL}/ws/v1/transcribe` } });
  const ctx = state.context;
  const readiness = useReadiness();
  const engines = useMemo(() => readiness.data?.engines ?? [], [readiness.data]);

  const active = state.matches("active");
  const streaming = state.matches({ active: "streaming" });
  const busy = active && !streaming && !state.matches({ active: "reconnecting" });
  const elapsed = useElapsed(ctx.startedAt, active);

  // Prefer the real engine; fall back to the fake one on a dev server without a Sarvam key.
  useEffect(() => {
    if (engines.length && !engines.includes(ctx.engine)) send({ type: "SET_ENGINE", engine: engines[0] });
  }, [engines, ctx.engine, send]);

  const transcriptEnd = useRef<HTMLDivElement>(null);
  useEffect(() => {
    transcriptEnd.current?.scrollIntoView({ block: "nearest" });
  }, [ctx.segments.length, ctx.partial]);

  const status = state.matches({ active: "requestingMic" })
    ? "Waiting for microphone permission…"
    : state.matches({ active: "connecting" })
      ? "Connecting to the transcription service…"
      : streaming
        ? "Listening"
        : state.matches({ active: "reconnecting" })
          ? `Connection lost. Reconnecting (attempt ${ctx.reconnectAttempt} of 3)…`
          : state.matches({ active: "stopping" })
            ? "Finishing the last sentence…"
            : state.matches("done") && ctx.doneReason
              ? DONE_TEXT[ctx.doneReason]
              : state.matches("error")
                ? (ctx.failure?.message ?? "Something went wrong.")
                : "Ready to record";

  const hasTranscript = ctx.segments.length > 0 || ctx.partial;

  return (
    <section className="space-y-6" aria-label="Live transcription">
      <div className="space-y-4 rounded-xl border p-5">
        <ScriptPicker value={ctx.script} onChange={(script) => send({ type: "SET_SCRIPT", script })} disabled={active} />

        {engines.length > 1 && (
          <label className="flex items-center gap-2 text-sm">
            <span className="font-medium">Engine</span>
            <select
              className="rounded-md border bg-background px-2 py-1"
              value={ctx.engine}
              onChange={(e) => send({ type: "SET_ENGINE", engine: e.target.value })}
              disabled={active}
            >
              {engines.map((name) => (
                <option key={name} value={name}>
                  {name === "fake" ? "fake (offline demo)" : name}
                </option>
              ))}
            </select>
          </label>
        )}

        <div className="flex items-center gap-3">
          {active ? (
            <Button
              size="lg"
              variant="destructive"
              onClick={() => send({ type: "STOP" })}
              disabled={state.matches({ active: "stopping" })}
            >
              {state.matches({ active: "stopping" }) ? <Loader2 className="animate-spin" /> : <Square />}
              Stop
            </Button>
          ) : (
            <Button size="lg" onClick={() => send({ type: "START" })}>
              <Mic />
              {state.matches("error") && ctx.failure?.retryable ? "Try again" : "Start recording"}
            </Button>
          )}
          {(state.matches("done") || state.matches("error")) && (
            <Button size="lg" variant="outline" onClick={() => send({ type: "RESET" })}>
              <RotateCcw />
              Clear
            </Button>
          )}
          <span className="ml-auto font-mono text-sm tabular-nums text-muted-foreground" aria-label="Elapsed time">
            {formatClock(elapsed)}
            {ctx.maxDurationS ? ` / ${formatClock(ctx.maxDurationS)}` : ""}
          </span>
        </div>

        <LevelMeter rms={ctx.level} active={streaming} />

        <p
          role="status"
          className={state.matches("error") ? "text-sm text-destructive" : "text-sm text-muted-foreground"}
        >
          {busy && <Loader2 className="mr-1.5 inline size-3.5 animate-spin" aria-hidden />}
          {status}
          {ctx.firstPartialMs !== null && (
            <span className="ml-2 rounded bg-muted px-1.5 py-0.5 text-xs">first text in {ctx.firstPartialMs} ms</span>
          )}
        </p>
      </div>

      <div className="min-h-48 rounded-xl border p-5">
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Transcript</h2>
        {hasTranscript ? (
          <div className="max-h-[50vh] space-y-2 overflow-y-auto text-lg leading-relaxed">
            <div aria-live="polite" aria-relevant="additions" className="space-y-2">
              {ctx.segments.map((seg) => (
                <p key={seg.key} lang={segmentLang(seg.text, seg.language)}>
                  {seg.text}
                </p>
              ))}
            </div>
            {/* Partials change several times a second; keep them out of the live region. */}
            {ctx.partial && (
              <p className="text-muted-foreground italic" aria-hidden>
                {ctx.partial}
              </p>
            )}
            <div ref={transcriptEnd} />
          </div>
        ) : (
          <p className="text-muted-foreground">
            Speak in Hindi, English or both. Text appears here as you talk.
          </p>
        )}
      </div>

      <p className="text-xs text-muted-foreground">
        Your audio is streamed to Sarvam AI for transcription and is never stored.
      </p>
    </section>
  );
}
