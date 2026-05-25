import { Circle, CheckCircle2, Archive, AlertCircle, Pencil } from "lucide-react";
import type { ComponentType, SVGProps } from "react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/cn";

type StatusKind = "active" | "draft" | "archived" | "pending" | "error" | "neutral";

type IconType = ComponentType<SVGProps<SVGSVGElement>>;

const KIND_MAP: Record<StatusKind, { icon: IconType; classes: string }> = {
  active: {
    icon: CheckCircle2,
    classes: "border-success/40 bg-success/10 text-success",
  },
  draft: {
    icon: Pencil,
    classes: "border-warning/40 bg-warning/10 text-warning",
  },
  archived: {
    icon: Archive,
    classes: "border-status-neutral/40 bg-status-neutral/10 text-status-neutral",
  },
  pending: {
    icon: Circle,
    classes: "border-info/40 bg-info/10 text-info",
  },
  error: {
    icon: AlertCircle,
    classes: "border-danger/40 bg-danger/10 text-danger",
  },
  neutral: {
    icon: Circle,
    classes: "border-border bg-muted text-muted-foreground",
  },
};

const STATUS_TO_KIND: Record<string, StatusKind> = {
  active: "active",
  confirmed: "active",
  paid: "active",
  balance_paid: "active",
  deposit_paid: "active",
  checked_in: "active",
  checked_out: "active",
  draft: "draft",
  archived: "archived",
  pending: "pending",
  pending_owner_approval: "pending",
  awaiting: "pending",
  awaiting_deposit: "pending",
  awaiting_balance: "pending",
  hold: "pending",
  cancelled: "error",
  canceled: "error",
  declined: "error",
  expired: "error",
  overdue: "error",
};

interface StatusBadgeProps {
  status: string;
  kind?: StatusKind;
  className?: string;
}

export function StatusBadge({ status, kind, className }: StatusBadgeProps) {
  const resolved = kind ?? STATUS_TO_KIND[status.toLowerCase()] ?? "neutral";
  const { icon: Icon, classes } = KIND_MAP[resolved];
  return (
    <Badge variant="outline" className={cn("gap-1 font-medium capitalize", classes, className)}>
      <Icon className="size-3.5" aria-hidden />
      <span>{status}</span>
    </Badge>
  );
}
