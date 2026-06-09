import { useState, type ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/cn";

interface CollapsibleProps {
  /** Header content shown on the left of the toggle row. */
  title: ReactNode;
  /** Open on first render. Defaults to collapsed. */
  defaultOpen?: boolean;
  /** Accessible name for the toggle when `title` is not plain text. */
  toggleAriaLabel?: string;
  /** Container classes. */
  className?: string;
  /** Toggle-button classes (layout / typography of the header row). */
  headerClassName?: string;
  /**
   * Body — mounted only while open, so any data hooks rendered inside stay
   * dormant until the operator expands the panel.
   */
  children: ReactNode;
}

/**
 * Minimal disclosure: a toggle row plus a body that mounts only while open.
 * Centralises the open-state, `aria-expanded`, and conditional-mount that the
 * enquiry-workspace rail and the guest enquiry-history aside both need, so the
 * a11y wiring lives in one place rather than being re-hand-rolled per panel.
 */
export function Collapsible({
  title,
  defaultOpen = false,
  toggleAriaLabel,
  className,
  headerClassName,
  children,
}: CollapsibleProps) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={className}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label={toggleAriaLabel}
        className={cn("flex w-full items-center justify-between", headerClassName)}
      >
        {title}
        <ChevronRight className={cn("size-4 shrink-0 transition-transform", open && "rotate-90")} />
      </button>
      {open ? children : null}
    </div>
  );
}
