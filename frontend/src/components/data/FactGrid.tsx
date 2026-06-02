import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/**
 * Denser sibling to {@link FactList}: a label-over-value pair laid out in a
 * responsive grid rather than one full-width row each. Use for compact detail
 * panels (Overview tab, rails). Keep `FactList` for genuinely linear or
 * long-value data where a row-per-fact reads better.
 */
export function FactGridItem({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="space-y-0.5 py-1">
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className="text-sm">{value}</dd>
    </div>
  );
}

const COLUMN_CLASS = {
  2: "sm:grid-cols-2",
  3: "sm:grid-cols-3",
} as const;

export function FactGrid({
  children,
  columns = 2,
  className,
}: {
  children: ReactNode;
  columns?: 2 | 3;
  className?: string;
}) {
  return (
    <dl className={cn("grid grid-cols-1 gap-x-6 gap-y-1", COLUMN_CLASS[columns], className)}>
      {children}
    </dl>
  );
}
