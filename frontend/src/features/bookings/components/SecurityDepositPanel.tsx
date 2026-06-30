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
import { formatDate } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/money";
import type { BookingId } from "@/lib/query/keys";
import { useReleaseSecurityDeposit, useSecurityDeposit } from "../hooks";
import { CaptureForDamagesDialog } from "./CaptureForDamagesDialog";
import {
  securityDepositKindLabel,
  securityDepositStatusLabel,
  type SecurityDeposit,
} from "../schemas";

interface Props {
  bookingId: BookingId;
  currency: string | null;
  /** True when the operator may move SD money (accounts role). */
  canWrite: boolean;
}

// Release / capture only make sense while money is actually held; every other
// status is either pre-money (awaiting) or terminal (already settled).
function isActionable(deposit: SecurityDeposit): boolean {
  return deposit.status === "pre_authed" || deposit.status === "held";
}

export function SecurityDepositPanel({ bookingId, currency, canWrite }: Props) {
  const { t } = useTranslation("bookings");
  const query = useSecurityDeposit(bookingId);
  const releaseMutation = useReleaseSecurityDeposit(bookingId);

  const [releasing, setReleasing] = useState(false);
  const [capturing, setCapturing] = useState(false);

  const deposit = query.data ?? null;

  const handleRelease = async () => {
    try {
      await releaseMutation.mutateAsync();
      toast.success(t("security_deposit.toasts.released"));
      setReleasing(false);
    } catch {
      toast.error(t("security_deposit.toasts.release_failed"));
    }
  };

  return (
    <section className="space-y-2">
      <h3 className="text-foreground text-base font-semibold">{t("security_deposit.title")}</h3>

      {query.isLoading ? (
        <Skeleton className="h-24 w-full" />
      ) : query.isError ? (
        <ErrorState
          title={t("security_deposit.load_failed_title")}
          description={t("security_deposit.load_failed_body")}
          onRetry={() => query.refetch()}
        />
      ) : deposit === null ? (
        <EmptyState
          title={t("security_deposit.empty_title")}
          description={t("security_deposit.empty_description")}
        />
      ) : (
        <div className="border-border bg-card space-y-3 rounded-lg border p-4">
          <div className="flex items-center justify-between gap-3">
            <div className="space-y-0.5">
              <div className="font-mono text-xs">{deposit.reference}</div>
              <div className="text-muted-foreground text-sm">
                {securityDepositKindLabel(deposit.kind)}
              </div>
            </div>
            <StatusBadge
              status={deposit.status}
              label={securityDepositStatusLabel(deposit.status)}
            />
          </div>

          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
            <dt className="text-muted-foreground">{t("security_deposit.fields.amount")}</dt>
            <dd className="text-right tabular-nums">
              {formatMoney(deposit.amount, deposit.currency_code ?? currency)}
            </dd>

            {deposit.kind === "pre_auth_hold" && deposit.hold_expires_at ? (
              <>
                <dt className="text-muted-foreground">
                  {t("security_deposit.fields.hold_expires_at")}
                </dt>
                <dd className="text-right">{formatDate(deposit.hold_expires_at)}</dd>
              </>
            ) : null}

            {deposit.release_scheduled_for ? (
              <>
                <dt className="text-muted-foreground">
                  {t("security_deposit.fields.release_scheduled_for")}
                </dt>
                <dd className="text-right">{formatDate(deposit.release_scheduled_for)}</dd>
              </>
            ) : null}

            {deposit.captured_amount != null ? (
              <>
                <dt className="text-muted-foreground">
                  {t("security_deposit.fields.captured_amount")}
                </dt>
                <dd className="text-right tabular-nums">
                  {formatMoney(deposit.captured_amount, deposit.currency_code ?? currency)}
                </dd>
              </>
            ) : null}

            {deposit.refunded_amount != null ? (
              <>
                <dt className="text-muted-foreground">
                  {t("security_deposit.fields.refunded_amount")}
                </dt>
                <dd className="text-right tabular-nums">
                  {formatMoney(deposit.refunded_amount, deposit.currency_code ?? currency)}
                </dd>
              </>
            ) : null}
          </dl>

          {isActionable(deposit) ? (
            <div className="flex justify-end gap-2">
              {canWrite ? (
                <>
                  <Button variant="outline" size="sm" onClick={() => setReleasing(true)}>
                    {t("security_deposit.actions.release")}
                  </Button>
                  <Button size="sm" onClick={() => setCapturing(true)}>
                    {t("security_deposit.actions.capture")}
                  </Button>
                </>
              ) : (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="flex gap-2">
                      <Button variant="outline" size="sm" disabled>
                        {t("security_deposit.actions.release")}
                      </Button>
                      <Button size="sm" disabled>
                        {t("security_deposit.actions.capture")}
                      </Button>
                    </span>
                  </TooltipTrigger>
                  <TooltipContent>{t("security_deposit.role_required_tooltip")}</TooltipContent>
                </Tooltip>
              )}
            </div>
          ) : null}
        </div>
      )}

      {releasing ? (
        <ConfirmDialog
          open
          onOpenChange={setReleasing}
          onConfirm={handleRelease}
          busy={releaseMutation.isPending}
          title={t("security_deposit.confirm_release.title")}
          description={t("security_deposit.confirm_release.description")}
          confirmLabel={t("security_deposit.confirm_release.confirm_label")}
        />
      ) : null}

      {capturing && deposit ? (
        <CaptureForDamagesDialog
          bookingId={bookingId}
          deposit={deposit}
          currencyCode={deposit.currency_code ?? currency}
          open
          onOpenChange={setCapturing}
        />
      ) : null}
    </section>
  );
}
