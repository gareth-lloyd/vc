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
import { ApiError } from "@/lib/api/errors";
import { formatDate } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/money";
import type { BookingId } from "@/lib/query/keys";
import { useApproveDamageClaim, useBookingDamageClaims, useWithdrawDamageClaim } from "../hooks";
import { DamageClaimFormDialog } from "./DamageClaimFormDialog";
import { DamageClaimPhotosDialog } from "./DamageClaimPhotosDialog";
import { damageClaimStatusLabel, type DamageClaim } from "../schemas";

interface Props {
  bookingId: BookingId;
  currency: string | null;
  canWrite: boolean;
}

export function DamageClaimsSection({ bookingId, currency, canWrite }: Props) {
  const { t } = useTranslation("bookings");
  const claims = useBookingDamageClaims(bookingId);
  const approveMutation = useApproveDamageClaim(bookingId);
  const withdrawMutation = useWithdrawDamageClaim(bookingId);

  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<DamageClaim | null>(null);
  const [approving, setApproving] = useState<DamageClaim | null>(null);
  const [withdrawing, setWithdrawing] = useState<DamageClaim | null>(null);
  const [viewingPhotos, setViewingPhotos] = useState<DamageClaim | null>(null);

  const rows = claims.data?.results ?? [];

  const handleApprove = async () => {
    if (!approving) return;
    try {
      await approveMutation.mutateAsync({ claimId: approving.id });
      toast.success(t("damage_claims.toasts.approved"));
      setApproving(null);
    } catch (err) {
      // Surface the state-machine's own 409 message (e.g. "Cannot move a
      // settled claim to approved.") verbatim; fall back to a generic toast.
      const message =
        err instanceof ApiError && err.isClientError() && err.detail
          ? err.detail
          : t("damage_claims.toasts.approve_failed");
      toast.error(message);
    }
  };

  const handleWithdraw = async () => {
    if (!withdrawing) return;
    try {
      await withdrawMutation.mutateAsync({ claimId: withdrawing.id });
      toast.success(t("damage_claims.toasts.withdrawn"));
      setWithdrawing(null);
    } catch {
      toast.error(t("damage_claims.toasts.withdraw_failed"));
    }
  };

  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-foreground text-base font-semibold">{t("damage_claims.title")}</h3>
        {canWrite ? (
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            {t("damage_claims.file")}
          </Button>
        ) : (
          <Tooltip>
            <TooltipTrigger asChild>
              <span>
                <Button size="sm" disabled>
                  {t("damage_claims.file")}
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent>{t("damage_claims.role_required_tooltip")}</TooltipContent>
          </Tooltip>
        )}
      </div>

      {claims.isLoading ? (
        <Skeleton className="h-24 w-full" />
      ) : claims.isError ? (
        <ErrorState
          title={t("damage_claims.load_failed_title")}
          description={t("damage_claims.load_failed_body")}
          onRetry={() => claims.refetch()}
        />
      ) : rows.length === 0 ? (
        <EmptyState
          title={t("damage_claims.empty_title")}
          description={t("damage_claims.empty_description")}
        />
      ) : (
        <div className="border-border bg-card overflow-hidden rounded-lg border">
          <table className="w-full text-sm">
            <thead className="border-border bg-muted/40 border-b">
              <tr>
                <th className="px-4 py-2 text-left font-medium">
                  {t("damage_claims.columns.reference")}
                </th>
                <th className="px-4 py-2 text-left font-medium">
                  {t("damage_claims.columns.description")}
                </th>
                <th className="px-4 py-2 text-left font-medium">
                  {t("damage_claims.columns.status")}
                </th>
                <th className="px-4 py-2 text-right font-medium">
                  {t("damage_claims.columns.amount")}
                </th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody className="divide-border divide-y">
              {rows.map((claim) => (
                <tr key={claim.id}>
                  <td className="px-4 py-2 font-mono text-xs">{claim.reference}</td>
                  <td className="px-4 py-2">
                    <div className="font-medium">{claim.description}</div>
                    <div className="text-muted-foreground text-xs">
                      {formatDate(claim.created_at)}
                    </div>
                  </td>
                  <td className="px-4 py-2">
                    <StatusBadge
                      status={claim.status}
                      label={damageClaimStatusLabel(claim.status)}
                    />
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums">
                    {formatMoney(claim.amount, claim.currency_code ?? currency)}
                  </td>
                  <td className="px-4 py-2 text-right">
                    {/* Row actions follow the claim state machine: OPEN is fully
                        editable (edit / approve / withdraw); APPROVED can only
                        be withdrawn; SETTLED and WITHDRAWN are terminal — no
                        actions. The server enforces the same transitions.
                        Photos are viewable by any staff (upload/delete gated
                        inside the dialog), so that button sits outside canWrite. */}
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label={t("damage_claims.row.photos_for", {
                          reference: claim.reference,
                        })}
                        onClick={() => setViewingPhotos(claim)}
                      >
                        {t("damage_claims.row.photos", { count: claim.photos.length })}
                      </Button>
                      {canWrite ? (
                        <>
                          {claim.status === "open" ? (
                            <>
                              <Button
                                variant="ghost"
                                size="sm"
                                aria-label={t("damage_claims.row.edit_for", {
                                  reference: claim.reference,
                                })}
                                onClick={() => setEditing(claim)}
                              >
                                {t("common:actions.edit")}
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                aria-label={t("damage_claims.row.approve_for", {
                                  reference: claim.reference,
                                })}
                                onClick={() => setApproving(claim)}
                              >
                                {t("damage_claims.row.approve")}
                              </Button>
                            </>
                          ) : null}
                          {claim.status === "open" || claim.status === "approved" ? (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="text-destructive"
                              aria-label={t("damage_claims.row.withdraw_for", {
                                reference: claim.reference,
                              })}
                              onClick={() => setWithdrawing(claim)}
                            >
                              {t("damage_claims.row.withdraw")}
                            </Button>
                          ) : null}
                        </>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {createOpen ? (
        <DamageClaimFormDialog
          mode="create"
          bookingId={bookingId}
          currencyCode={currency}
          open={createOpen}
          onOpenChange={setCreateOpen}
        />
      ) : null}

      {editing ? (
        <DamageClaimFormDialog
          mode="edit"
          bookingId={bookingId}
          currencyCode={editing.currency_code ?? currency}
          claim={editing}
          open
          onOpenChange={(open) => {
            if (!open) setEditing(null);
          }}
        />
      ) : null}

      {viewingPhotos ? (
        <DamageClaimPhotosDialog
          bookingId={bookingId}
          claimId={viewingPhotos.id}
          claimReference={viewingPhotos.reference}
          canWrite={canWrite}
          open
          onOpenChange={(open) => {
            if (!open) setViewingPhotos(null);
          }}
        />
      ) : null}

      {approving ? (
        <ConfirmDialog
          open
          onOpenChange={(open) => {
            if (!open) setApproving(null);
          }}
          onConfirm={handleApprove}
          busy={approveMutation.isPending}
          title={t("damage_claims.confirm_approve.title")}
          description={t("damage_claims.confirm_approve.description", {
            reference: approving.reference,
          })}
          confirmLabel={t("damage_claims.confirm_approve.confirm_label")}
        />
      ) : null}

      {withdrawing ? (
        <ConfirmDialog
          open
          onOpenChange={(open) => {
            if (!open) setWithdrawing(null);
          }}
          onConfirm={handleWithdraw}
          destructive
          busy={withdrawMutation.isPending}
          title={t("damage_claims.confirm_withdraw.title")}
          description={t("damage_claims.confirm_withdraw.description", {
            reference: withdrawing.reference,
          })}
          confirmLabel={t("damage_claims.confirm_withdraw.confirm_label")}
        />
      ) : null}
    </section>
  );
}
