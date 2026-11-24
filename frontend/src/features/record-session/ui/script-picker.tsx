"use client";

import type { ScriptMode } from "@/shared/lib/realtime/protocol";
import { cn } from "@/shared/lib/utils";

const OPTIONS: { value: ScriptMode; label: string; example: string; lang: string }[] = [
  { value: "mixed", label: "Mixed", example: "आज की meeting", lang: "hi" },
  { value: "devanagari", label: "Devanagari", example: "आज की मीटिंग", lang: "hi" },
  { value: "roman", label: "Roman", example: "aaj ki meeting", lang: "hi-Latn" },
];

interface ScriptPickerProps {
  value: ScriptMode;
  onChange(value: ScriptMode): void;
  disabled?: boolean;
}

/** Output script for final segments. Partials always arrive as plain transcription. */
export function ScriptPicker({ value, onChange, disabled }: ScriptPickerProps) {
  return (
    <fieldset disabled={disabled} className="space-y-2">
      <legend className="text-sm font-medium">Output script</legend>
      <div className="grid grid-cols-3 gap-2">
        {OPTIONS.map((opt) => (
          <label
            key={opt.value}
            className={cn(
              "flex cursor-pointer flex-col rounded-lg border px-3 py-2 text-sm transition-colors",
              "has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-ring/50",
              value === opt.value ? "border-primary bg-primary/5" : "hover:bg-muted",
              disabled && "cursor-not-allowed opacity-60",
            )}
          >
            <input
              type="radio"
              name="script"
              value={opt.value}
              checked={value === opt.value}
              onChange={() => onChange(opt.value)}
              className="sr-only"
            />
            <span className="font-medium">{opt.label}</span>
            <span lang={opt.lang} className="text-muted-foreground">
              {opt.example}
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
