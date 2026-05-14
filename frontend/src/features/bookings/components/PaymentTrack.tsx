import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/data/StatusBadge";
import { ApiError } from "@/lib/api/errors";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/format/date";
import { formatMoney, parseMoney } from "@/lib/format/money";
import type { BookingId } from "@/lib/query/keys";
import type { TrackName } from "../api";
import { useRequestPayment } from "../hooks";
import { paymentTrackStatusLabel, type PaymentTrack as PaymentTrackData } from "../schemas";
import { PaymentActionDialog } from "./PaymentActionDialog";

interface PaymentTrackProps {
  bookingId: BookingId;
  trackName: TrackName;
  trackLabel: string;
  data: PaymentTrackData | undefined;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  currency: string | null;
  canWrite: boolean;
}

function GateButton({
  canWrite,
  tooltipMessage,
  children,
  ...buttonProps
}: {
  canWrite: boolean;
  tooltipMessage: string;
  children: ReactNode;
} & React.ComponentProps<typeof Button>) {
  if (canWrite) {
    return <Button {...buttonProps}>{children}</Button>;
  }
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span>
          <Button {...buttonProps} disabled>
            {children}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>{tooltipMessage}</TooltipContent>
    </Tooltip>
  );
}

function MilestoneRow({ data, ariaLabel }: { data: PaymentTrackData; ariaLabel: string }) {
  const scheduled = parseMoney(data.scheduled_amount);
  const paid = parseMoney(data.paid_amount);
  const ratio =
    Number.isFinite(scheduled) && scheduled > 0
      ? Math.min(1, Math.max(0, paid / scheduled))
      : data.status === "succeeded" || data.status === "waived"
        ? 1
        : 0;
  const filled = Math.round(ratio * 6);
  return (
    <div className="flex items-center gap-1" aria-label={ariaLabel}>
      {Array.from({ length: 6 }).map((_, i) => (
        <span
          key={i}
          className={cn("size-2.5 rounded-full", i < filled ? "bg-emerald-500" : "bg-muted")}
        />
      ))}
    </div>
  );
}

export function PaymentTrack({
  bookingId,
  trackName,
  trackLabel,
  data,
  isLoading,
  isError,
  onRetry,
  currency,
  canWrite,
}: PaymentTrackProps) {
  const { t } = useTranslation("bookings");
  const [markPaidOpen, setMarkPaidOpen] = useState(false);
  const [waiveOpen, setWaiveOpen] = useState(false);
  const requestMutation = useRequestPayment(bookingId, trackName);

  const handleRequest = async () => {
    try {
      await requestMutation.mutateAsync();
      toast.success(t("payments.track.toasts.request_success", { track: trackLabel }));
    } catch (error) {
      if (error instanceof ApiError && error.status === 501) {
        toast.error(t("payments.track.toasts.request_not_wired"));
      } else if (error instanceof ApiError) {
        toast.error(error.detail);
      } else {
        toast.error(t("common:errors.generic"));
      }
    }
  };

  if (isLoading) {
    return (
      <section className="border-border bg-card space-y-3 rounded-lg border p-4">
        <Skeleton className="h-5 w-1/3" />
        <Skeleton className="h-4 w-1/2" />
      </section>
    );
  }

  if (isError || !data) {
    return (
      <section className="border-border bg-card space-y-3 rounded-lg border p-4">
        <div className="flex items-center justify-between">
          <h3 className="font-medium">{trackLabel}</h3>
          <Button variant="outline" size="sm" onClick={onRetry}>
            {t("common:actions.retry")}
          </Button>
        </div>
        <p className="text-muted-foreground text-sm">{t("payments.track.load_failed")}</p>
      </section>
    );
  }

  const scheduled = parseMoney(data.scheduled_amount);
  const paid = parseMoney(data.paid_amount);
  const remaining =
    Number.isFinite(scheduled) && Number.isFinite(paid) ? Math.max(0, scheduled - paid) : null;
  const due = data.due_at ? new Date(data.due_at) : null;
  const isOverdue =
    due != null &&
    due.getTime() < Date.now() &&
    data.status !== "succeeded" &&
    data.status !== "waived";

  const remainingDefault =
    remaining != null && Number.isFinite(remaining) ? remaining.toFixed(2) : undefined;

  const tooltipMessage = t("payments.track.role_required_tooltip");

  return (
    <section className="border-border bg-card space-y-3 rounded-lg border p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <h3 className="font-medium">{trackLabel}</h3>
          <p className="text-muted-foreground text-sm">
            {t("payments.track.summary", {
              paid: formatMoney(paid, currency),
              total: formatMoney(scheduled, currency),
            })}
          </p>
        </div>
        <StatusBadge status={paymentTrackStatusLabel(data.status) ?? data.status} />
      </div>

      <div className="flex items-center justify-between gap-3">
        <MilestoneRow data={data} ariaLabel={t("payments.track.milestones_aria")} />
        {due ? (
          <span
            className={cn(
              "text-xs",
              isOverdue ? "text-destructive font-medium" : "text-muted-foreground",
            )}
          >
            {t("payments.track.due_label", { date: formatDate(due.toISOString()) })}
            {isOverdue ? t("payments.track.overdue_suffix") : ""}
          </span>
        ) : (
          <span className="text-muted-foreground text-xs">{t("payments.track.no_due_date")}</span>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-end gap-2 pt-1">
        <GateButton
          canWrite={canWrite}
          tooltipMessage={tooltipMessage}
          variant="outline"
          size="sm"
          onClick={handleRequest}
          disabled={
            requestMutation.isPending || data.status === "succeeded" || data.status === "waived"
          }
        >
          {data.status === "pending"
            ? t("payments.track.send_reminder")
            : t("payments.track.request_payment")}
        </GateButton>
        <GateButton
          canWrite={canWrite}
          tooltipMessage={tooltipMessage}
          size="sm"
          onClick={() => setMarkPaidOpen(true)}
          disabled={data.status === "succeeded" || data.status === "waived"}
        >
          {t("payments.track.mark_received")}
        </GateButton>
        <GateButton
          canWrite={canWrite}
          tooltipMessage={tooltipMessage}
          variant="outline"
          size="sm"
          onClick={() => setWaiveOpen(true)}
          disabled={data.status === "succeeded" || data.status === "waived"}
        >
          {t("payments.track.waive")}
        </GateButton>
      </div>

      {markPaidOpen ? (
        <PaymentActionDialog
          bookingId={bookingId}
          track={trackName}
          trackLabel={trackLabel}
          action="mark-paid"
          open={markPaidOpen}
          onOpenChange={setMarkPaidOpen}
          defaultAmount={remainingDefault}
        />
      ) : null}
      {waiveOpen ? (
        <PaymentActionDialog
          bookingId={bookingId}
          track={trackName}
          trackLabel={trackLabel}
          action="waive"
          open={waiveOpen}
          onOpenChange={setWaiveOpen}
        />
      ) : null}
    </section>
  );
}
