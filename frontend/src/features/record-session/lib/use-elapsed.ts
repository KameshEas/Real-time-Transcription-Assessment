"use client";

import { useEffect, useState } from "react";

/**
 * Seconds since `startedAt`, ticking while `running`; frozen at the last value when stopped.
 * The clock is read only inside the interval (never during render), so prerendering stays deterministic.
 */
export function useElapsed(startedAt: number | null, running: boolean): number {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(id);
  }, [running]);
  return startedAt && now ? Math.max(0, Math.floor((now - startedAt) / 1000)) : 0;
}

export function formatClock(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}
