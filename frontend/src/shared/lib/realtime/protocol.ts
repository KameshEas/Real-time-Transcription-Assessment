/**
 * Realtime protocol v1 for /ws/v1/transcribe. Mirrors backend `transcription/interface/protocol_v1.py`.
 * JSON messages carry `v: 1`; audio goes up as binary frames (PCM16 mono 16 kHz, ~100 ms each).
 */

export type ScriptMode = "mixed" | "devanagari" | "roman";

export interface StartMessage {
  v: 1;
  type: "start";
  engine: string;
  script: ScriptMode;
  resume_transcript_id?: string;
  passcode?: string;
}

export type ClientMessage = StartMessage | { v: 1; type: "stop" } | { v: 1; type: "ping" };

export type ErrorCode =
  | "BAD_MESSAGE"
  | "START_REQUIRED"
  | "FRAME_INVALID"
  | "FRAME_TOO_LARGE"
  | "IDLE_TIMEOUT"
  | "ENGINE_NOT_AVAILABLE"
  | "ENGINE_UNAVAILABLE"
  | "ENGINE_AUTH"
  | "ENGINE_QUOTA"
  | "ENGINE_CONFIG"
  | "ENGINE_IDLE_TIMEOUT"
  | "ENGINE_ERROR"
  | "STORAGE_UNAVAILABLE"
  | "SAVE_FAILED";

export type DoneReason = "stopped" | "limit" | "engine_closed" | "error" | "idle";

export type ServerMessage =
  | {
      v: 1;
      type: "ready";
      session_id: string;
      /** The transcript every final is saved into; send it back as `resume_transcript_id` after a drop. */
      transcript_id: string;
      resumed: boolean;
      last_seq: number;
      engine: string;
      script: ScriptMode;
      max_duration_s: number;
    }
  | { v: 1; type: "partial"; utterance: number; text: string }
  | {
      v: 1;
      type: "final";
      seq: number;
      utterance: number;
      text: string;
      language: string | null;
      /** False when the database write failed; the text is still shown. */
      saved: boolean;
    }
  | { v: 1; type: "latency"; first_partial_ms: number }
  | { v: 1; type: "limit"; reason: "max_duration"; max_duration_s: number }
  | { v: 1; type: "error"; code: ErrorCode; message: string; fatal: boolean; retryable: boolean }
  | {
      v: 1;
      type: "done";
      reason: DoneReason;
      transcript_id: string;
      segments: number;
      duration_ms: number;
      dropped_partials: number;
    }
  | { v: 1; type: "pong" };

export function parseServerMessage(raw: string): ServerMessage | null {
  try {
    const msg = JSON.parse(raw) as { v?: unknown; type?: unknown };
    return msg.v === 1 && typeof msg.type === "string" ? (msg as ServerMessage) : null;
  } catch {
    return null;
  }
}
