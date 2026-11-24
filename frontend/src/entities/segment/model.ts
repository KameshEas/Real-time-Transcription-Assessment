export interface LiveSegment {
  /** Stable key across reconnects (server `seq` restarts per connection). */
  key: number;
  text: string;
  /** BCP-47 from the engine, e.g. "hi-IN", when it detected one. */
  language: string | null;
}

const DEVANAGARI = /[ऀ-ॿ]/;

/** The `lang` to put on a segment so screen readers and fonts pick the right voice and glyphs. */
export function segmentLang(text: string, language: string | null): string | undefined {
  if (DEVANAGARI.test(text)) return "hi";
  if (language?.startsWith("hi")) return "hi-Latn"; // Romanized Hindi
  return language ?? undefined;
}
