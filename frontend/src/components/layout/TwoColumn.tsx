import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

interface TwoColumnProps {
  children: ReactNode;
  rightRail: ReactNode;
  className?: string;
}

export function TwoColumn({ children, rightRail, className }: TwoColumnProps) {
  return (
    <div className={cn("flex w-full gap-6 px-6 py-6", className)}>
      <div className="min-w-0 flex-1">{children}</div>
      <aside className="hidden w-[340px] shrink-0 lg:block">
        <div className="border-border bg-card sticky top-6 rounded-lg border p-4">{rightRail}</div>
      </aside>
    </div>
  );
}
