import { cn } from "@/shared/lib/utils";

/** Mic input level. `rms` is 0..1; speech usually sits around 0.02–0.2, so the scale is boosted. */
export function LevelMeter({ rms, active, className }: { rms: number; active: boolean; className?: string }) {
  const pct = active ? Math.min(100, Math.round(Math.sqrt(rms) * 220)) : 0;
  return (
    <div
      className={cn("h-1.5 w-full overflow-hidden rounded-full bg-muted", className)}
      role="meter"
      aria-label="Microphone level"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={pct}
    >
      <div className="h-full rounded-full bg-emerald-500 transition-[width] duration-100" style={{ width: `${pct}%` }} />
    </div>
  );
}
