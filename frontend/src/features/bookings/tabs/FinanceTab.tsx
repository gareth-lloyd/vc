import { useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { FactList, FactRow } from "@/components/data/FactList";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { formatDate } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/money";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { useBookingChargeItems, useDeleteChargeItem } from "../hooks";
import { ChargeItemFormDialog } from "../components/ChargeItemFormDialog";
import {
  pricingSnapshotSchema,
  type BookingChargeItem,
  type PricingSnapshot,
  type PricingSnapshotLine,
} from "../schemas";
import type { BookingOutletContext } from "../BookingDetailLayout";

function parseSnapshot(value: unknown): PricingSnapshot | null {
  if (!value || typeof value !== "object") return null;
  const parsed = pricingSnapshotSchema.safeParse(value);
  return parsed.success ? parsed.data : null;
}

function pickMoney(snapshot: PricingSnapshot, keys: (keyof PricingSnapshot)[]): unknown {
  for (const key of keys) {
    const v = snapshot[key];
    if (v != null && v !== "") return v;
  }
  return null;
}

function moneyOrNull(value: unknown, currency: string | null | undefined) {
  if (value == null || value === "") return null;
  if (typeof value === "number" || typeof value === "string") {
    return formatMoney(value, currency ?? null);
  }
  return null;
}

function SnapshotSection({
  snapshot,
  currency,
}: {
  snapshot: PricingSnapshot;
  currency: string | null;
}) {
  const { t } = useTranslation("bookings");

  const rows: Array<{ label: string; value: string }> = [];
  const push = (label: string, raw: unknown) => {
    const formatted = moneyOrNull(raw, currency);
    if (formatted != null) rows.push({ label, value: formatted });
  };

  // Plain non-money facts first
  if (snapshot.date_from || snapshot.date_to) {
    rows.push({
      label: t("finance.fields.dates"),
      value: `${formatDate(snapshot.date_from)} – ${formatDate(snapshot.date_to)}`,
    });
  }
  if (snapshot.nights != null) {
    rows.push({ label: t("finance.fields.nights"), value: String(snapshot.nights) });
  }

  push(t("finance.fields.nightly_rate"), pickMoney(snapshot, ["nightly_rate"]));
  push(t("finance.fields.rate_subtotal"), pickMoney(snapshot, ["rate_subtotal"]));
  push(t("finance.fields.extras_total"), pickMoney(snapshot, ["extras_total"]));
  push(t("finance.fields.fees"), pickMoney(snapshot, ["fees"]));
  push(t("finance.fields.adjustments"), pickMoney(snapshot, ["adjustments"]));
  push(t("finance.fields.discount"), pickMoney(snapshot, ["discount"]));
  push(t("finance.fields.commission"), pickMoney(snapshot, ["commission"]));
  push(t("finance.fields.tax"), pickMoney(snapshot, ["tax", "taxes"]));
  push(t("finance.fields.deposit"), pickMoney(snapshot, ["deposit"]));
  push(t("finance.fields.balance"), pickMoney(snapshot, ["balance"]));
  push(t("finance.fields.security"), pickMoney(snapshot, ["security", "security_deposit"]));
  push(t("finance.fields.total"), pickMoney(snapshot, ["grand_total", "total"]));

  const lines: PricingSnapshotLine[] = snapshot.lines ?? [];

  return (
    <>
      {rows.length > 0 ? (
        <FactList>
          {rows.map((row) => (
            <FactRow key={row.label} label={row.label} value={row.value} />
          ))}
        </FactList>
      ) : (
        <EmptyState title={t("finance.empty.title")} description={t("finance.empty.description")} />
      )}

      {lines.length > 0 ? (
        <section className="space-y-2">
          <h3 className="text-foreground text-base font-semibold">{t("finance.lines.title")}</h3>
          <div className="border-border bg-card overflow-hidden rounded-lg border">
            <table className="w-full text-sm">
              <thead className="border-border bg-muted/40 border-b">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">{t("finance.lines.label")}</th>
                  <th className="px-4 py-2 text-right font-medium">
                    {t("finance.lines.quantity")}
                  </th>
                  <th className="px-4 py-2 text-right font-medium">
                    {t("finance.lines.unit_price")}
                  </th>
                  <th className="px-4 py-2 text-right font-medium">{t("finance.lines.total")}</th>
                </tr>
              </thead>
              <tbody className="divide-border divide-y">
                {lines.map((line, idx) => (
                  <tr key={idx}>
                    <td className="px-4 py-2">{line.label ?? line.description ?? "—"}</td>
                    <td className="px-4 py-2 text-right">
                      {line.quantity != null ? String(line.quantity) : "—"}
                    </td>
                    <td className="px-4 py-2 text-right">
                      {moneyOrNull(line.unit_price, currency) ?? "—"}
                    </td>
                    <td className="px-4 py-2 text-right">
                      {moneyOrNull(line.total, currency) ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      <div
        role="note"
        className="border-border bg-muted/30 text-muted-foreground rounded-lg border px-4 py-3 text-sm"
      >
        {t("finance.alert")}
      </div>
    </>
  );
}

export function FinanceTab() {
  const { t } = useTranslation("bookings");
  const { booking } = useOutletContext<BookingOutletContext>();
  const canWrite = useHasReservationsRole();

  const snapshot = useMemo(
    () => parseSnapshot(booking.pricing_snapshot),
    [booking.pricing_snapshot],
  );
  const currency = booking.currency_code ?? null;

  const charges = useBookingChargeItems(booking.id);
  const deleteMutation = useDeleteChargeItem(booking.id);
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<BookingChargeItem | null>(null);
  const [deleting, setDeleting] = useState<BookingChargeItem | null>(null);

  const chargeRows = charges.data?.results ?? [];

  const handleDelete = async () => {
    if (!deleting) return;
    try {
      await deleteMutation.mutateAsync({ itemId: deleting.id });
      toast.success(t("finance.charges.toasts.removed"));
      setDeleting(null);
    } catch {
      toast.error(t("finance.charges.toasts.remove_failed"));
    }
  };

  return (
    <div className="space-y-6 p-6">
      <h2 className="text-foreground text-lg font-semibold">{t("finance.title")}</h2>

      {snapshot ? (
        <SnapshotSection snapshot={snapshot} currency={snapshot.currency_code ?? currency} />
      ) : (
        <EmptyState title={t("finance.empty.title")} description={t("finance.empty.description")} />
      )}

      {/* Manual charges live outside the immutable snapshot, so this section
          renders snapshot-or-not — legacy-imported bookings (no snapshot) are
          prime users of ad-hoc charges. */}
      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h3 className="text-foreground text-base font-semibold">{t("finance.charges.title")}</h3>
          {canWrite ? (
            <Button size="sm" onClick={() => setCreateOpen(true)}>
              {t("finance.charges.add")}
            </Button>
          ) : (
            <Tooltip>
              <TooltipTrigger asChild>
                <span>
                  <Button size="sm" disabled>
                    {t("finance.charges.add")}
                  </Button>
                </span>
              </TooltipTrigger>
              <TooltipContent>{t("finance.charges.role_required_tooltip")}</TooltipContent>
            </Tooltip>
          )}
        </div>

        {charges.isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : charges.isError ? (
          <ErrorState
            title={t("finance.charges.load_failed_title")}
            description={t("finance.charges.load_failed_body")}
            onRetry={() => charges.refetch()}
          />
        ) : chargeRows.length === 0 ? (
          <EmptyState
            title={t("finance.charges.empty_title")}
            description={t("finance.charges.empty_description")}
          />
        ) : (
          <div className="border-border bg-card overflow-hidden rounded-lg border">
            <table className="w-full text-sm">
              <thead className="border-border bg-muted/40 border-b">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">
                    {t("finance.charges.columns.label")}
                  </th>
                  <th className="px-4 py-2 text-left font-medium">
                    {t("finance.charges.columns.notes")}
                  </th>
                  <th className="px-4 py-2 text-right font-medium">
                    {t("finance.charges.columns.amount")}
                  </th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody className="divide-border divide-y">
                {chargeRows.map((item) => (
                  <tr key={item.id}>
                    <td className="px-4 py-2 font-medium">
                      {item.label}
                      {item.commissionable === false ? (
                        <span className="text-muted-foreground ml-2 text-xs font-normal italic">
                          {t("finance.charges.non_commissionable")}
                        </span>
                      ) : null}
                    </td>
                    <td className="text-muted-foreground px-4 py-2">{item.notes || "—"}</td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {formatMoney(item.amount, currency)}
                    </td>
                    <td className="px-4 py-2 text-right">
                      {canWrite ? (
                        <div className="flex justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            aria-label={t("finance.charges.row.edit_for", { label: item.label })}
                            onClick={() => setEditing(item)}
                          >
                            {t("common:actions.edit")}
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-destructive"
                            aria-label={t("finance.charges.row.delete_for", {
                              label: item.label,
                            })}
                            onClick={() => setDeleting(item)}
                          >
                            {t("common:actions.delete")}
                          </Button>
                        </div>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {chargeRows.length > 0 ? (
          <FactList>
            {booking.charges_total != null ? (
              <FactRow
                label={t("finance.charges.charges_total")}
                value={formatMoney(booking.charges_total, currency) ?? booking.charges_total}
              />
            ) : null}
            {booking.total != null ? (
              <FactRow
                label={t("finance.charges.total_with_charges")}
                value={formatMoney(booking.total, currency) ?? booking.total}
              />
            ) : null}
          </FactList>
        ) : null}
      </section>

      {createOpen ? (
        <ChargeItemFormDialog
          mode="create"
          bookingId={booking.id}
          currencyCode={currency}
          open={createOpen}
          onOpenChange={setCreateOpen}
        />
      ) : null}

      {editing ? (
        <ChargeItemFormDialog
          mode="edit"
          bookingId={booking.id}
          currencyCode={currency}
          item={editing}
          open
          onOpenChange={(open) => {
            if (!open) setEditing(null);
          }}
        />
      ) : null}

      {deleting ? (
        <ConfirmDialog
          open
          onOpenChange={(open) => {
            if (!open) setDeleting(null);
          }}
          onConfirm={handleDelete}
          title={t("finance.charges.confirm_delete.title")}
          description={t("finance.charges.confirm_delete.description")}
          confirmLabel={t("finance.charges.confirm_delete.confirm_label")}
          destructive
          busy={deleteMutation.isPending}
        />
      ) : null}
    </div>
  );
}
