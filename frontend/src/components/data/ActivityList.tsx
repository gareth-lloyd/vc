import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/**
 * The shared card shell for vertical lists of rows (timelines, audit logs,
 * detail lists): a bordered, divided card surface. Presentational only —
 * callers pass already-translated children. Use `as="ol"` for chronological
 * lists where order is meaningful.
 */
export function ActivityList({
  as: Tag = "ul",
  children,
  className,
}: {
  as?: "ul" | "ol" | "dl";
  children: ReactNode;
  className?: string;
}) {
  return (
    <Tag
      className={cn("border-border bg-card divide-border divide-y rounded-lg border", className)}
    >
      {children}
    </Tag>
  );
}
