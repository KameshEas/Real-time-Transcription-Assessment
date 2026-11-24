/**
 * The side-effecting half of a recording: owns the mic and the gateway socket for one session.
 * Invoked by the recorder machine; talks back only through events, so the machine stays the single
 * source of truth for UI state.
 */
import { fromCallback } from "xstate";

import { MicError, startMicCapture, type MicCapture, type MicErrorCode } from "@/shared/lib/audio/mic-capture";
import type { DoneReason, ErrorCode, ScriptMode } from "@/shared/lib/realtime/protocol";
import { TranscribeSocket } from "@/shared/lib/realtime/transcribe-socket";

export type FailureCode = ErrorCode | MicErrorCode | "CONNECTION_FAILED" | "CONNECTION_LOST";

export interface Failure {
  code: FailureCode;
  message: string;
  retryable: boolean;
}

export type LiveSessionEvent =
  | { type: "MIC_READY" }
  | { type: "READY"; sessionId: string; maxDurationS: number }
  | { type: "PARTIAL"; text: string }
  | { type: "FINAL"; text: string; language: string | null }
  | { type: "LATENCY"; ms: number }
  | { type: "LEVEL"; rms: number }
  | { type: "LIMIT"; maxDurationS: number }
  | { type: "RECONNECTING"; attempt: number }
  | { type: "DONE"; reason: DoneReason }
  | { type: "FAILED"; failure: Failure };

export interface LiveSessionInput {
  url: string;
  engine: string;
  script: ScriptMode;
}

const MAX_RECONNECTS = 3;

export const liveSession = fromCallback<{ type: "STOP" }, LiveSessionInput, LiveSessionEvent>(
  ({ input, sendBack, receive }) => {
    let disposed = false;
    let stopping = false;
    let failed = false;
    let everReady = false;
    let attempts = 0;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let mic: MicCapture | null = null;
    let socket: TranscribeSocket | null = null;

    const fail = (failure: Failure) => {
      if (failed || disposed) return;
      failed = true;
      sendBack({ type: "FAILED", failure });
    };

    const connect = () => {
      socket = new TranscribeSocket(input.url, {
        onMessage(msg) {
          switch (msg.type) {
            case "ready":
              everReady = true;
              attempts = 0;
              sendBack({ type: "READY", sessionId: msg.session_id, maxDurationS: msg.max_duration_s });
              break;
            case "partial":
              sendBack({ type: "PARTIAL", text: msg.text });
              break;
            case "final":
              sendBack({ type: "FINAL", text: msg.text, language: msg.language });
              break;
            case "latency":
              sendBack({ type: "LATENCY", ms: msg.first_partial_ms });
              break;
            case "limit":
              stopping = true;
              sendBack({ type: "LIMIT", maxDurationS: msg.max_duration_s });
              break;
            case "error":
              // Retryable fatal errors end in a close, which reconnects; the rest are terminal.
              if (msg.fatal && !msg.retryable) {
                fail({ code: msg.code, message: msg.message, retryable: false });
              }
              break;
            case "done":
              if (!failed) sendBack({ type: "DONE", reason: msg.reason });
              break;
          }
        },
        onClose({ expected }) {
          if (disposed || expected || failed) return;
          if (stopping) {
            sendBack({ type: "DONE", reason: "stopped" });
          } else if (!everReady) {
            fail({ code: "CONNECTION_FAILED", message: "Can't reach the transcription server.", retryable: true });
          } else if (attempts < MAX_RECONNECTS) {
            attempts++;
            sendBack({ type: "RECONNECTING", attempt: attempts });
            retryTimer = setTimeout(connect, 500 * 2 ** attempts);
          } else {
            fail({ code: "CONNECTION_LOST", message: "The connection dropped and could not be restored.", retryable: true });
          }
        },
      });
      socket.open({ v: 1, type: "start", engine: input.engine, script: input.script });
    };

    void (async () => {
      try {
        mic = await startMicCapture({
          onFrame: (frame) => socket?.sendAudio(frame),
          onLevel: (rms) => sendBack({ type: "LEVEL", rms }),
        });
      } catch (err) {
        const e = err instanceof MicError ? err : new MicError("MIC_FAILED", "The microphone could not be opened.");
        fail({ code: e.code, message: e.message, retryable: e.code !== "MIC_UNSUPPORTED" });
        return;
      }
      if (disposed) {
        await mic.stop();
        return;
      }
      sendBack({ type: "MIC_READY" });
      connect();
    })();

    receive((event) => {
      if (event.type !== "STOP" || stopping) return;
      stopping = true;
      if (!socket?.isOpen) {
        // Mid-reconnect: nothing to finalize server-side.
        clearTimeout(retryTimer);
        sendBack({ type: "DONE", reason: "stopped" });
        return;
      }
      // Flush the last audio frame first, then ask the server to finalize.
      void (mic?.stop() ?? Promise.resolve()).then(() => socket?.stop());
    });

    return () => {
      disposed = true;
      clearTimeout(retryTimer);
      void mic?.stop();
      socket?.close();
    };
  },
);
