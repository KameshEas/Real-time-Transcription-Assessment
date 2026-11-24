"use client";

import { useReadiness } from "@/shared/api/health";

export function BackendStatus() {
  const { data, isPending, isError } = useReadiness();

  const label = isPending ? "Checking backend…" : isError ? "Backend unreachable" : "Backend ready";
  const dot = isPending ? "bg-amber-400" : isError ? "bg-red-500" : "bg-emerald-500";

  return (
    <div className="rounded-lg border p-4 text-sm" role="status" aria-live="polite">
      <p className="flex items-center gap-2 font-medium">
        <span className={`size-2 rounded-full ${dot}`} aria-hidden />
        {label}
      </p>
      {data && (
        <ul className="mt-3 space-y-1 text-muted-foreground">
          <li>Roles: {data.roles.join(", ")}</li>
          {Object.entries(data.vendors).map(([name, ok]) => (
            <li key={name}>
              {name}: {ok ? "configured" : "missing key"}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
