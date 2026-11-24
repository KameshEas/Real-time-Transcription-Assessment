/**
 * Recording lifecycle (ARCHITECTURE §14):
 *   idle → active.requestingMic → active.connecting → active.streaming ⇄ active.reconnecting
 *        → active.stopping → done            (any active state → error on failure)
 * Leaving `active` stops the invoked live-session actor, which releases the mic and closes the socket,
 * so the UI can never show "recording" without a live mic or vice versa.
 */
import { assign, sendTo, setup } from "xstate";

import type { LiveSegment } from "@/entities/segment";
import type { DoneReason, ScriptMode } from "@/shared/lib/realtime/protocol";

import { liveSession, type Failure, type LiveSessionEvent } from "./live-session";

export interface RecorderContext {
  url: string;
  engine: string;
  script: ScriptMode;
  segments: LiveSegment[];
  partial: string;
  level: number;
  firstPartialMs: number | null;
  startedAt: number | null;
  maxDurationS: number | null;
  reconnectAttempt: number;
  doneReason: DoneReason | null;
  failure: Failure | null;
}

export type RecorderEvent =
  | { type: "START" }
  | { type: "STOP" }
  | { type: "RESET" }
  | { type: "SET_SCRIPT"; script: ScriptMode }
  | { type: "SET_ENGINE"; engine: string }
  | LiveSessionEvent;

const fresh = {
  segments: [],
  partial: "",
  level: 0,
  firstPartialMs: null,
  startedAt: null,
  maxDurationS: null,
  reconnectAttempt: 0,
  doneReason: null,
  failure: null,
} satisfies Partial<RecorderContext>;

const settingsEvents = {
  SET_SCRIPT: { actions: "setScript" },
  SET_ENGINE: { actions: "setEngine" },
} as const;

export const recorderMachine = setup({
  types: {
    context: {} as RecorderContext,
    events: {} as RecorderEvent,
    input: {} as { url: string; engine?: string; script?: ScriptMode },
  },
  actors: { liveSession },
  actions: {
    beginSession: assign(() => ({ ...fresh })),
    stopSession: sendTo("session", { type: "STOP" }),
    setScript: assign({
      script: ({ context, event }) => (event.type === "SET_SCRIPT" ? event.script : context.script),
    }),
    setEngine: assign({
      engine: ({ context, event }) => (event.type === "SET_ENGINE" ? event.engine : context.engine),
    }),
  },
}).createMachine({
  id: "recorder",
  context: ({ input }) => ({
    url: input.url,
    engine: input.engine ?? "sarvam",
    script: input.script ?? "mixed",
    ...fresh,
  }),
  initial: "idle",
  states: {
    idle: {
      on: { START: { target: "active", actions: "beginSession" }, ...settingsEvents },
    },
    active: {
      invoke: {
        id: "session",
        src: "liveSession",
        input: ({ context }) => ({ url: context.url, engine: context.engine, script: context.script }),
      },
      initial: "requestingMic",
      on: {
        PARTIAL: { actions: assign({ partial: ({ event }) => event.text }) },
        FINAL: {
          actions: assign({
            segments: ({ context, event }) => [
              ...context.segments,
              { key: context.segments.length, text: event.text, language: event.language },
            ],
            partial: "",
          }),
        },
        LATENCY: { actions: assign({ firstPartialMs: ({ context, event }) => context.firstPartialMs ?? event.ms }) },
        LEVEL: { actions: assign({ level: ({ event }) => event.rms }) },
        DONE: { target: "done", actions: assign({ doneReason: ({ event }) => event.reason, partial: "", level: 0 }) },
        FAILED: { target: "error", actions: assign({ failure: ({ event }) => event.failure, level: 0 }) },
      },
      states: {
        requestingMic: {
          on: { MIC_READY: "connecting", STOP: "#recorder.idle" },
        },
        connecting: {
          on: {
            READY: {
              target: "streaming",
              actions: assign({
                startedAt: ({ context }) => context.startedAt ?? Date.now(),
                maxDurationS: ({ event }) => event.maxDurationS,
              }),
            },
            STOP: "#recorder.idle",
          },
        },
        streaming: {
          on: {
            STOP: { target: "stopping", actions: "stopSession" },
            LIMIT: "stopping",
            RECONNECTING: {
              target: "reconnecting",
              actions: assign({ reconnectAttempt: ({ event }) => event.attempt, partial: "" }),
            },
          },
        },
        reconnecting: {
          on: {
            READY: { target: "streaming", actions: assign({ reconnectAttempt: 0 }) },
            RECONNECTING: { actions: assign({ reconnectAttempt: ({ event }) => event.attempt }) },
            STOP: { target: "stopping", actions: "stopSession" },
          },
        },
        stopping: {
          // The server normally answers within a second or two; never hang the UI on it.
          after: { 20_000: { target: "#recorder.done", actions: assign({ doneReason: "stopped" }) } },
        },
      },
    },
    done: {
      on: {
        START: { target: "active", actions: "beginSession" },
        RESET: { target: "idle", actions: "beginSession" },
        ...settingsEvents,
      },
    },
    error: {
      on: {
        START: { target: "active", actions: "beginSession" },
        RESET: { target: "idle", actions: "beginSession" },
        ...settingsEvents,
      },
    },
  },
});
