import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { ActivityList } from "./ActivityList";

export function FactRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="grid grid-cols-3 gap-4 py-2 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="col-span-2">{value}</dd>
    </div>
  );
}

export function FactList({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <ActivityList as="dl" className={cn("px-4", className)}>
      {children}
    </ActivityList>
  );
}
