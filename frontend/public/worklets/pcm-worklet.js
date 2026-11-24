/**
 * Mic -> 16 kHz mono PCM16 frames of 100 ms (1,600 samples = 3,200 bytes), the format the gateway expects.
 *
 * Runs at the AudioContext's native rate (usually 48 kHz or 44.1 kHz) and downsamples here, because
 * Firefox refuses to connect a mic stream to a context with a different sample rate. Each output sample
 * is the mean of the input samples it covers (a box filter), which removes most aliasing for speech.
 *
 * Posts { pcm: ArrayBuffer, level: number } where level is the frame's RMS (0..1).
 * Accepts the message "flush" to emit a final short frame.
 */
const TARGET_RATE = 16000;
const FRAME_SAMPLES = 1600;

class PcmWorklet extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / TARGET_RATE; // `sampleRate` is a global in AudioWorkletGlobalScope
    this.pending = new Float32Array(0);
    this.pos = 0;
    this.out = new Int16Array(FRAME_SAMPLES);
    this.outLen = 0;
    this.sumSq = 0;
    this.port.onmessage = (e) => {
      if (e.data === "flush") this.emit();
    };
  }

  emit() {
    if (this.outLen === 0) return;
    const pcm = this.out.slice(0, this.outLen).buffer;
    const level = Math.sqrt(this.sumSq / this.outLen);
    this.port.postMessage({ pcm, level }, [pcm]);
    this.outLen = 0;
    this.sumSq = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;

    const buf = new Float32Array(this.pending.length + channel.length);
    buf.set(this.pending);
    buf.set(channel, this.pending.length);

    let pos = this.pos;
    while (pos + this.ratio <= buf.length) {
      const end = pos + this.ratio;
      let acc = 0;
      let n = 0;
      for (let i = Math.floor(pos); i < Math.ceil(end); i++) {
        acc += buf[i];
        n++;
      }
      const s = Math.max(-1, Math.min(1, acc / n));
      this.out[this.outLen++] = s < 0 ? s * 0x8000 : s * 0x7fff;
      this.sumSq += s * s;
      if (this.outLen === FRAME_SAMPLES) this.emit();
      pos = end;
    }

    const keep = Math.floor(pos);
    this.pending = buf.slice(keep);
    this.pos = pos - keep;
    return true;
  }
}

registerProcessor("pcm-worklet", PcmWorklet);
