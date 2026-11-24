/** Captures the microphone as 16 kHz PCM16 frames of 100 ms via an AudioWorklet (see public/worklets). */

export type MicErrorCode = "MIC_DENIED" | "MIC_NOT_FOUND" | "MIC_UNSUPPORTED" | "MIC_FAILED";

export class MicError extends Error {
  constructor(public readonly code: MicErrorCode, message: string) {
    super(message);
  }
}

export interface MicCapture {
  /** Flushes the last partial frame, then releases the mic. */
  stop(): Promise<void>;
}

export interface MicCallbacks {
  onFrame(pcm: ArrayBuffer): void;
  onLevel?(rms: number): void;
}

const WORKLET_URL = "/worklets/pcm-worklet.js";

export async function startMicCapture({ onFrame, onLevel }: MicCallbacks): Promise<MicCapture> {
  if (typeof window === "undefined" || !navigator.mediaDevices?.getUserMedia || !window.AudioWorkletNode) {
    throw new MicError("MIC_UNSUPPORTED", "This browser can't record audio. Try a recent Chrome, Edge, Firefox or Safari.");
  }

  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
  } catch (err) {
    const name = err instanceof DOMException ? err.name : "";
    if (name === "NotAllowedError" || name === "SecurityError") {
      throw new MicError("MIC_DENIED", "Microphone access was blocked. Allow it in the browser's site settings.");
    }
    if (name === "NotFoundError" || name === "OverconstrainedError") {
      throw new MicError("MIC_NOT_FOUND", "No microphone was found.");
    }
    throw new MicError("MIC_FAILED", "The microphone could not be opened.");
  }

  const ctx = new AudioContext();
  try {
    await ctx.audioWorklet.addModule(WORKLET_URL);
    if (ctx.state === "suspended") await ctx.resume();

    const source = ctx.createMediaStreamSource(stream);
    const node = new AudioWorkletNode(ctx, "pcm-worklet", { numberOfInputs: 1, numberOfOutputs: 1 });
    // Some engines only pull nodes that reach the destination; a muted gain keeps it silent.
    const mute = ctx.createGain();
    mute.gain.value = 0;
    source.connect(node).connect(mute).connect(ctx.destination);

    node.port.onmessage = (e: MessageEvent<{ pcm: ArrayBuffer; level: number }>) => {
      onFrame(e.data.pcm);
      onLevel?.(e.data.level);
    };

    let stopped = false;
    return {
      async stop() {
        if (stopped) return;
        stopped = true;
        node.port.postMessage("flush");
        // Give the flush a moment to arrive before tearing down.
        await new Promise((r) => setTimeout(r, 50));
        node.port.onmessage = null;
        source.disconnect();
        node.disconnect();
        stream.getTracks().forEach((t) => t.stop());
        await ctx.close();
      },
    };
  } catch (err) {
    stream.getTracks().forEach((t) => t.stop());
    await ctx.close();
    throw err instanceof MicError ? err : new MicError("MIC_FAILED", "The audio pipeline could not start.");
  }
}
