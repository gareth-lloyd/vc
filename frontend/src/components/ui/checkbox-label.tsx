import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/**
 * The shared inline row pairing a Checkbox with its label text. The caller
 * supplies the <Checkbox/> and (already-translated) label as children; the
 * wrapping <label> makes the whole row a click target for the control.
 */
export function CheckboxLabel({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={cn("flex cursor-pointer items-center gap-2 text-sm", className)}>
      {children}
    </label>
  );
}
