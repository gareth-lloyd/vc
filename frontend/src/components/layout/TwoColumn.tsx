import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

interface TwoColumnProps {
  children: ReactNode;
  rightRail: ReactNode;
  className?: string;
  /**
   * Collapse the rail to `display:none` at every width, letting the main column
   * fill. The rail subtree stays **mounted** (state preserved) — used by the
   * enquiry builder to go full-width without discarding rail panel state.
   * Default `false` keeps the usual "hidden below lg, shown from lg" behaviour.
   */
  hideRail?: boolean;
}

export function TwoColumn({ children, rightRail, className, hideRail = false }: TwoColumnProps) {
  return (
    <div className={cn("flex w-full gap-6 px-6 py-6", className)}>
      <div className="min-w-0 flex-1">{children}</div>
      <aside className={cn("w-[340px] shrink-0", hideRail ? "hidden" : "hidden lg:block")}>
        <div className="border-border bg-card sticky top-6 rounded-lg border p-4">{rightRail}</div>
      </aside>
    </div>
  );
}
