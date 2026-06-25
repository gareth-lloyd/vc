import { Circle, CheckCircle2, Archive, AlertCircle, Pencil } from "lucide-react";
import type { ComponentType, SVGProps } from "react";
import { cva } from "class-variance-authority";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/cn";

type StatusKind = "active" | "draft" | "archived" | "pending" | "error" | "neutral";

type IconType = ComponentType<SVGProps<SVGSVGElement>>;

const statusBadgeVariants = cva("gap-1 font-medium", {
  variants: {
    kind: {
      active: "border-success/40 bg-success/10 text-success",
      draft: "border-warning/40 bg-warning/10 text-warning",
      archived: "border-status-neutral/40 bg-status-neutral/10 text-status-neutral",
      pending: "border-info/40 bg-info/10 text-info",
      error: "border-danger/40 bg-danger/10 text-danger",
      neutral: "border-border bg-muted text-muted-foreground",
    },
  },
  defaultVariants: {
    kind: "neutral",
  },
});

const KIND_ICON: Record<StatusKind, IconType> = {
  active: CheckCircle2,
  draft: Pencil,
  archived: Archive,
  pending: Circle,
  error: AlertCircle,
  neutral: Circle,
};

const STATUS_TO_KIND: Record<string, StatusKind> = {
  active: "active",
  confirmed: "active",
  paid: "active",
  balance_paid: "active",
  deposit_paid: "active",
  checked_in: "active",
  checked_out: "active",
  succeeded: "active",
  draft: "draft",
  archived: "archived",
  waived: "archived",
  pending: "pending",
  pending_owner_approval: "pending",
  awaiting: "pending",
  awaiting_deposit: "pending",
  awaiting_balance: "pending",
  hold: "pending",
  open: "pending",
  approved: "active",
  settled: "active",
  withdrawn: "archived",
  cancelled: "error",
  canceled: "error",
  declined: "error",
  expired: "error",
  failed: "error",
  overdue: "error",
};

interface StatusBadgeProps {
  status: string;
  /** Humanised display text; the visual kind still keys on the raw status. */
  label?: string;
  kind?: StatusKind;
  className?: string;
}

export function StatusBadge({ status, label, kind, className }: StatusBadgeProps) {
  const resolved = kind ?? STATUS_TO_KIND[status.toLowerCase()] ?? "neutral";
  const Icon = KIND_ICON[resolved];
  return (
    <Badge variant="outline" className={cn(statusBadgeVariants({ kind: resolved }), className)}>
      <Icon className="size-3.5" aria-hidden />
      {/* A provided label renders verbatim; a raw status keeps the legacy
          CSS capitalisation so unlabelled call sites don't regress. */}
      <span className={label ? undefined : "capitalize"}>{label ?? status}</span>
    </Badge>
  );
}
