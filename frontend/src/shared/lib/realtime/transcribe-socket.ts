import { parseServerMessage, type ClientMessage, type ServerMessage, type StartMessage } from "./protocol";

const HEARTBEAT_MS = 15_000;
/** Above this many queued bytes (~4 s of audio) new frames are dropped instead of piling up. */
const MAX_BUFFERED_BYTES = 128 * 1024;
/** Frames captured before the server is `ready` (engine handshake ~2 s) are held, up to ~5 s of audio. */
const MAX_BACKLOG_FRAMES = 50;

export interface SocketCloseInfo {
  code: number;
  /** True when the server finished the session (sent `done`) or we closed it on purpose. */
  expected: boolean;
}

export interface TranscribeSocketHandlers {
  onMessage(msg: ServerMessage): void;
  onClose(info: SocketCloseInfo): void;
}

/** One WebSocket connection to the gateway: sends `start`, keeps a heartbeat, streams audio frames. */
export class TranscribeSocket {
  private ws: WebSocket | null = null;
  private heartbeat: ReturnType<typeof setInterval> | null = null;
  private finished = false;
  private ready = false;
  private backlog: ArrayBuffer[] = [];
  droppedFrames = 0;

  constructor(
    private readonly url: string,
    private readonly handlers: TranscribeSocketHandlers,
  ) {}

  open(start: StartMessage): void {
    const ws = new WebSocket(this.url);
    ws.binaryType = "arraybuffer";
    this.ws = ws;

    ws.onopen = () => {
      this.send(start);
      this.heartbeat = setInterval(() => this.send({ v: 1, type: "ping" }), HEARTBEAT_MS);
    };
    ws.onmessage = (e: MessageEvent) => {
      if (typeof e.data !== "string") return;
      const msg = parseServerMessage(e.data);
      if (!msg) return;
      if (msg.type === "done") this.finished = true;
      if (msg.type === "ready") this.flushBacklog();
      this.handlers.onMessage(msg);
    };
    ws.onclose = (e: CloseEvent) => {
      this.clearHeartbeat();
      this.ws = null;
      this.handlers.onClose({ code: e.code, expected: this.finished });
    };
    // `onerror` is always followed by `onclose`, which carries what we need.
  }

  get isOpen(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  /** Sends a frame, or holds it until the server is ready so the user's first words aren't lost. */
  sendAudio(frame: ArrayBuffer): void {
    if (!this.ready) {
      this.backlog.push(frame);
      if (this.backlog.length > MAX_BACKLOG_FRAMES) this.backlog.shift();
      return;
    }
    const ws = this.ws;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (ws.bufferedAmount > MAX_BUFFERED_BYTES) {
      this.droppedFrames++;
      return;
    }
    ws.send(frame);
  }

  /** Ask the server to finalize; it answers with the last `final`s and `done`, then closes. */
  stop(): void {
    this.send({ v: 1, type: "stop" });
  }

  close(): void {
    this.finished = true;
    this.clearHeartbeat();
    this.ws?.close(1000);
    this.ws = null;
    this.backlog = [];
  }

  private flushBacklog(): void {
    this.ready = true;
    const frames = this.backlog;
    this.backlog = [];
    frames.forEach((f) => this.sendAudio(f));
  }

  private send(msg: ClientMessage): void {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(msg));
  }

  private clearHeartbeat(): void {
    if (this.heartbeat) clearInterval(this.heartbeat);
    this.heartbeat = null;
  }
}
