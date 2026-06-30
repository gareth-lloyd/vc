import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { StatusBadge } from "@/components/data/StatusBadge";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { formatDate } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/money";
import type { BookingId } from "@/lib/query/keys";
import { useBookingRefunds } from "../hooks";
import { RefundFormDialog } from "./RefundFormDialog";
import { refundMethodLabel, refundStatusLabel } from "../schemas";

interface Props {
  bookingId: BookingId;
  currency: string | null;
  canWrite: boolean;
}

export function RefundsSection({ bookingId, currency, canWrite }: Props) {
  const { t } = useTranslation("bookings");
  const refunds = useBookingRefunds(bookingId);
  const [createOpen, setCreateOpen] = useState(false);

  const rows = refunds.data ?? [];

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
    </section>
  );
}
