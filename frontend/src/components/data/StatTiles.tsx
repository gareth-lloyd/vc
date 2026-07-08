import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/**
 * A compact row of at-a-glance metric tiles — the mock-up's "four-stat row"
 * (Total / Paid / Due / …). Values are rendered in the serif numeral face with
 * tabular figures; an optional tone tints the value via the status palette.
 * Money values must arrive pre-formatted through `formatMoney` (currency code
 * included).
 */
export type StatTone = "default" | "success" | "warning" | "danger" | "info" | "muted";

const TONE_CLASS: Record<StatTone, string> = {
  default: "text-foreground",
  success: "text-success",
  warning: "text-warning",
  danger: "text-danger",
  info: "text-info",
  muted: "text-muted-foreground",
};

// Column counts respond to the tiles' own container width (not the viewport),
// so the fixed-width booking rail stacks the money boxes into a single column
// while the roomy Overview column keeps them side-by-side. Thresholds are set
// so a side-by-side box is always wide enough for a full money figure.
const COLUMN_CLASS: Record<number, string> = {
  1: "grid-cols-1",
  2: "grid-cols-1 @[340px]:grid-cols-2",
  3: "grid-cols-1 @[460px]:grid-cols-3",
  4: "grid-cols-2 @[560px]:grid-cols-4",
};

export interface StatTileData {
  label: string;
  value: ReactNode;
  tone?: StatTone;
  hint?: string;
}

export function StatTiles({ tiles, className }: { tiles: StatTileData[]; className?: string }) {
  const columns = COLUMN_CLASS[Math.min(tiles.length, 4)] ?? COLUMN_CLASS[4];
  return (
    <div className={cn("@container", className)}>
      <dl className={cn("grid gap-3", columns)}>
        {tiles.map((tile) => (
          <div
            key={tile.label}
            className="border-border bg-card shadow-card min-w-0 rounded-lg border px-3 py-2"
          >
            <dt className="text-muted-foreground text-xs">{tile.label}</dt>
            <dd
              className={cn(
                "truncate font-serif text-lg tabular-nums",
                TONE_CLASS[tile.tone ?? "default"],
              )}
            >
              {tile.value}
            </dd>
            {tile.hint ? <p className="text-muted-foreground mt-0.5 text-xs">{tile.hint}</p> : null}
          </div>
        ))}
      </dl>
    </div>
  );
}
