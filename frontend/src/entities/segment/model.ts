export interface LiveSegment {
  /** Stable React key: position in the live list (unsaved sentences have no `seq`). */
  key: number;
  text: string;
  /** BCP-47 from the engine, e.g. "hi-IN", when it detected one. */
  language: string | null;
  /** Server-side segment number; null if the sentence couldn't be saved. */
  seq: number | null;
}

const DEVANAGARI = /[ऀ-ॿ]/;

/** The `lang` to put on a segment so screen readers and fonts pick the right voice and glyphs. */
export function segmentLang(text: string, language: string | null): string | undefined {
  if (DEVANAGARI.test(text)) return "hi";
  if (language?.startsWith("hi")) return "hi-Latn"; // Romanized Hindi
  return language ?? undefined;
}
