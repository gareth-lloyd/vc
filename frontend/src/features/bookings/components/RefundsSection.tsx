import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { StatusBadge } from "@/components/data/StatusBadge";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { useAuthStore } from "@/features/auth/store";
import { ApiError } from "@/lib/api/errors";
import { formatDate } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/money";
import type { BookingId } from "@/lib/query/keys";
import { useApproveRefund, useBookingRefunds, useCancelRefund, useExecuteRefund } from "../hooks";
import { RefundFormDialog } from "./RefundFormDialog";
import { RejectRefundDialog } from "./RejectRefundDialog";
import { refundMethodLabel, refundStatusLabel, type Refund } from "../schemas";

interface Props {
  bookingId: BookingId;
  currency: string | null;
  canWrite: boolean;
}

type ConfirmAction = "approve" | "execute" | "cancel";

export function RefundsSection({ bookingId, currency, canWrite }: Props) {
  const { t } = useTranslation("bookings");
  const refunds = useBookingRefunds(bookingId);
  // Separation of duties: the requester may never approve their own refund (the
  // backend enforces it; the FE disables Approve to surface it before the 403).
  const currentUserId = useAuthStore((s) => s.user?.id ?? null);

  const approveMutation = useApproveRefund(bookingId);
  const executeMutation = useExecuteRefund(bookingId);
  const cancelMutation = useCancelRefund(bookingId);

  const [createOpen, setCreateOpen] = useState(false);
  const [rejecting, setRejecting] = useState<Refund | null>(null);
  const [confirming, setConfirming] = useState<{ action: ConfirmAction; refund: Refund } | null>(
    null,
  );

  const rows = refunds.data ?? [];
  const actionBusy =
    approveMutation.isPending || executeMutation.isPending || cancelMutation.isPending;

  const handleConfirm = async () => {
    if (!confirming) return;
    const { action, refund } = confirming;
    try {
      if (action === "approve") await approveMutation.mutateAsync({ refundId: refund.id });
      else if (action === "execute") await executeMutation.mutateAsync({ refundId: refund.id });
      else await cancelMutation.mutateAsync({ refundId: refund.id });
      const toastKey =
        action === "approve" ? "approved" : action === "execute" ? "executed" : "cancelled";
      toast.success(t(`refunds.toasts.${toastKey}`));
      setConfirming(null);
    } catch (error) {
      // Surface the backend's specific reason on a 4xx (e.g. a 409
      // "Refund is not in an executable state." when a colleague already moved
      // it, or a separation-of-duties 403) rather than a generic message;
      // fall back to the generic copy on 5xx/network.
      const message =
        error instanceof ApiError && error.isClientError()
          ? error.detail
          : t("refunds.toasts.action_failed");
      toast.error(message);
    }
  };

  const confirmCopy = (() => {
    if (!confirming) return null;
    const { action, refund } = confirming;
    if (action === "approve") {
      return {
        title: t("refunds.confirm_approve.title"),
        description: t("refunds.confirm_approve.description", { reference: refund.reference }),
        confirmLabel: t("refunds.confirm_approve.confirm_label"),
        destructive: false,
      };
    }
    if (action === "execute") {
      return {
        title: t("refunds.confirm_execute.title"),
        description: t("refunds.confirm_execute.description", {
          amount: formatMoney(refund.amount, currency),
        }),
        confirmLabel: t("refunds.confirm_execute.confirm_label"),
        destructive: false,
      };
    }
    return {
      title: t("refunds.confirm_cancel.title"),
      description: t("refunds.confirm_cancel.description", { reference: refund.reference }),
      confirmLabel: t("refunds.confirm_cancel.confirm_label"),
      destructive: true,
    };
  })();

  // The lifecycle decides which actions a row offers. `executing` and the
  // terminal statuses (succeeded/failed/rejected/cancelled) are read-only.
  function renderActions(refund: Refund) {
    if (!canWrite) return null;
    if (refund.status === "pending") {
      const isSelfRequester = currentUserId != null && refund.requested_by === currentUserId;
      return (
        <div className="flex justify-end gap-1">
          {isSelfRequester ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <span>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled
                    aria-label={t("refunds.row.approve_for", { reference: refund.reference })}
                  >
                    {t("refunds.row.approve")}
                  </Button>
                </span>
              </TooltipTrigger>
              <TooltipContent>{t("refunds.row.self_approve_tooltip")}</TooltipContent>
            </Tooltip>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              aria-label={t("refunds.row.approve_for", { reference: refund.reference })}
              onClick={() => setConfirming({ action: "approve", refund })}
            >
              {t("refunds.row.approve")}
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            aria-label={t("refunds.row.reject_for", { reference: refund.reference })}
            onClick={() => setRejecting(refund)}
          >
            {t("refunds.row.reject")}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="text-destructive"
            aria-label={t("refunds.row.cancel_for", { reference: refund.reference })}
            onClick={() => setConfirming({ action: "cancel", refund })}
          >
            {t("refunds.row.cancel")}
          </Button>
        </div>
      );
    }
    if (refund.status === "approved") {
      return (
        <div className="flex justify-end gap-1">
          <Button
            variant="ghost"
            size="sm"
            aria-label={t("refunds.row.execute_for", { reference: refund.reference })}
            onClick={() => setConfirming({ action: "execute", refund })}
          >
            {t("refunds.row.execute")}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="text-destructive"
            aria-label={t("refunds.row.cancel_for", { reference: refund.reference })}
            onClick={() => setConfirming({ action: "cancel", refund })}
          >
            {t("refunds.row.cancel")}
          </Button>
        </div>
      );
    }
    return null;
  }

  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-foreground text-base font-semibold">{t("refunds.title")}</h3>
        {canWrite ? (
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            {t("refunds.request")}
          </Button>
        ) : (
          <Tooltip>
            <TooltipTrigger asChild>
              <span>
                <Button size="sm" disabled>
                  {t("refunds.request")}
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent>{t("refunds.role_required_tooltip")}</TooltipContent>
          </Tooltip>
        )}
      </div>

      {refunds.isLoading ? (
        <Skeleton className="h-24 w-full" />
      ) : refunds.isError ? (
        <ErrorState
          title={t("refunds.load_failed_title")}
          description={t("refunds.load_failed_body")}
          onRetry={() => refunds.refetch()}
        />
      ) : rows.length === 0 ? (
        <EmptyState title={t("refunds.empty_title")} description={t("refunds.empty_description")} />
      ) : (
        <div className="border-border bg-card overflow-hidden rounded-lg border">
          <table className="w-full text-sm">
            <thead className="border-border bg-muted/40 border-b">
              <tr>
                <th className="px-4 py-2 text-left font-medium">
                  {t("refunds.columns.reference")}
                </th>
                <th className="px-4 py-2 text-left font-medium">{t("refunds.columns.status")}</th>
                <th className="px-4 py-2 text-left font-medium">{t("refunds.columns.method")}</th>
                <th className="px-4 py-2 text-right font-medium">{t("refunds.columns.amount")}</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody className="divide-border divide-y">
              {rows.map((refund) => (
                <tr key={refund.id}>
                  <td className="px-4 py-2">
                    <div className="font-mono text-xs">{refund.reference}</div>
                    <div className="text-muted-foreground text-xs">
                      {formatDate(refund.requested_at ?? refund.created_at)}
                    </div>
                  </td>
                  <td className="px-4 py-2">
                    <StatusBadge status={refund.status} label={refundStatusLabel(refund.status)} />
                  </td>
                  <td className="px-4 py-2">{refundMethodLabel(refund.method)}</td>
                  <td className="px-4 py-2 text-right tabular-nums">
                    {formatMoney(refund.amount, currency)}
                  </td>
                  <td className="px-4 py-2 text-right">{renderActions(refund)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {createOpen ? (
        <RefundFormDialog
          bookingId={bookingId}
          currencyCode={currency}
          open={createOpen}
          onOpenChange={setCreateOpen}
        />
      ) : null}

      {rejecting ? (
        <RejectRefundDialog
          bookingId={bookingId}
          refund={rejecting}
          open
          onOpenChange={(open) => {
            if (!open) setRejecting(null);
          }}
        />
      ) : null}

      {confirming && confirmCopy ? (
        <ConfirmDialog
          open
          onOpenChange={(open) => {
            if (!open) setConfirming(null);
          }}
          onConfirm={handleConfirm}
          busy={actionBusy}
          destructive={confirmCopy.destructive}
          title={confirmCopy.title}
          description={confirmCopy.description}
          confirmLabel={confirmCopy.confirmLabel}
        />
      ) : null}
    </section>
  );
}
