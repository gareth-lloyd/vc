import { Circle, CheckCircle2, Archive, AlertCircle, Pencil } from "lucide-react";
import type { ComponentType, SVGProps } from "react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/cn";

type StatusKind = "active" | "draft" | "archived" | "pending" | "error" | "neutral";

type IconType = ComponentType<SVGProps<SVGSVGElement>>;

const KIND_MAP: Record<StatusKind, { icon: IconType; classes: string }> = {
  active: {
    icon: CheckCircle2,
    classes: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  },
  draft: {
    icon: Pencil,
    classes: "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400",
  },
  archived: {
    icon: Archive,
    classes: "border-slate-500/40 bg-slate-500/10 text-slate-700 dark:text-slate-400",
  },
  pending: {
    icon: Circle,
    classes: "border-blue-500/40 bg-blue-500/10 text-blue-700 dark:text-blue-400",
  },
  error: {
    icon: AlertCircle,
    classes: "border-destructive/40 bg-destructive/10 text-destructive",
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
