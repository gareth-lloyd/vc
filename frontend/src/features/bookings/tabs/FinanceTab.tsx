import { useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Collapsible } from "@/components/ui/collapsible";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { FactList, FactRow } from "@/components/data/FactList";
import { StatusBadge } from "@/components/data/StatusBadge";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { formatDate } from "@/lib/format/date";
import { formatMoney, parseMoney } from "@/lib/format/money";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import {
  useBookingChargeItems,
  useDeleteChargeItem,
  useSecurityDeposit,
  useSetDepositOverride,
} from "../hooks";
import { ChargeItemFormDialog } from "../components/ChargeItemFormDialog";
import { DepositOverrideDialog } from "../components/DepositOverrideDialog";
import {
  pricingSnapshotSchema,
  securityDepositStatusLabel,
  type BookingChargeItem,
  type BookingNetToOwner,
  type PaymentComponentSplit,
  type PricingSnapshot,
  type PricingSnapshotLine,
} from "../schemas";
import type { BookingOutletContext } from "../BookingDetailLayout";

function parseSnapshot(value: unknown): PricingSnapshot | null {
  if (!value || typeof value !== "object") return null;
  const parsed = pricingSnapshotSchema.safeParse(value);
  return parsed.success ? parsed.data : null;
}

// Money rows SnapshotSection renders, in display order. snapshotHasContent
// derives its key set from this same list so the two can never drift (a key
// rendered but not counted would hide real data behind the empty state).
const SNAPSHOT_MONEY_ROWS: Array<{ labelKey: string; keys: (keyof PricingSnapshot)[] }> = [
  { labelKey: "finance.fields.nightly_rate", keys: ["nightly_rate"] },
  { labelKey: "finance.fields.rate_subtotal", keys: ["rate_subtotal"] },
  { labelKey: "finance.fields.extras_total", keys: ["extras_total"] },
  { labelKey: "finance.fields.fees", keys: ["fees"] },
  { labelKey: "finance.fields.adjustments", keys: ["adjustments"] },
  { labelKey: "finance.fields.discount", keys: ["discount"] },
  { labelKey: "finance.fields.commission", keys: ["commission"] },
  { labelKey: "finance.fields.tax", keys: ["tax", "taxes"] },
  { labelKey: "finance.fields.deposit", keys: ["deposit"] },
  { labelKey: "finance.fields.balance", keys: ["balance"] },
  { labelKey: "finance.fields.security", keys: ["security", "security_deposit"] },
  { labelKey: "finance.fields.total", keys: ["grand_total", "total"] },
];

// GAP-086 — a snapshot that would render zero rows and no lines (legacy
// imports often carry `{}`) is treated like a missing snapshot, so the empty
// state stays immediately visible instead of hiding inside the disclosure.
const SNAPSHOT_MONEY_KEYS = SNAPSHOT_MONEY_ROWS.flatMap((row) => row.keys);

function snapshotHasContent(snapshot: PricingSnapshot): boolean {
  if (snapshot.date_from || snapshot.date_to || snapshot.nights != null) return true;
  if ((snapshot.lines ?? []).length > 0) return true;
  return SNAPSHOT_MONEY_KEYS.some((key) => {
    const v = snapshot[key];
    return v != null && v !== "";
  });
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

  for (const row of SNAPSHOT_MONEY_ROWS) {
    push(t(row.labelKey), pickMoney(snapshot, row.keys));
  }

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

// The API guarantees 2-dp decimal strings, so integer cents keep the totals
// row exact where float addition of the raw numbers could drift.
function toCents(value: string): number {
  const parsed = parseMoney(value);
  return Number.isFinite(parsed) ? Math.round(parsed * 100) : Number.NaN;
}

// GAP-077 — per-component (deposit / balance) owner-money split of the payment
// schedule. Commission renders only under its explicit "Commission" header
// (finance.ts rule: never folded into another figure).
function PaymentSplitSection({
  splits,
  netToOwner,
  currency,
}: {
  splits: PaymentComponentSplit[];
  netToOwner: BookingNetToOwner | undefined;
  currency: string | null;
}) {
  const { t } = useTranslation("bookings");

  const purposeLabel = (purpose: PaymentComponentSplit["purpose"]): string => {
    if (purpose === "deposit") return t("finance.component_splits.purpose.deposit");
    if (purpose === "balance") return t("finance.component_splits.purpose.balance");
    return purpose;
  };

  const sum = (field: "gross" | "commission" | "tax" | "net_to_owner") =>
    splits.reduce((acc, row) => acc + toCents(row[field]), 0);
  const totals = {
    gross: sum("gross"),
    commission: sum("commission"),
    tax: sum("tax"),
    net_to_owner: sum("net_to_owner"),
  };
  // Σ split net can drift from the whole-booking net when the schedule has
  // been reshaped (partial mark-paid, manual rows) — caveat, don't reconcile.
  const netDrifted =
    netToOwner != null &&
    Number.isFinite(totals.net_to_owner) &&
    totals.net_to_owner !== toCents(netToOwner.net_to_owner);

  return (
    <section className="space-y-2">
      <h3 className="text-foreground text-base font-semibold">
        {t("finance.component_splits.title")}
      </h3>
      <div className="border-border bg-card overflow-hidden rounded-lg border">
        <table className="w-full text-sm">
          <thead className="border-border bg-muted/40 border-b">
            <tr>
              <th className="px-4 py-2 text-left font-medium">
                {t("finance.component_splits.columns.component")}
              </th>
              <th className="px-4 py-2 text-right font-medium">
                {t("finance.component_splits.columns.gross")}
              </th>
              <th className="px-4 py-2 text-right font-medium">
                {t("finance.component_splits.columns.commission")}
              </th>
              <th className="px-4 py-2 text-right font-medium">
                {t("finance.component_splits.columns.tax")}
              </th>
              <th className="px-4 py-2 text-right font-medium">
                {t("finance.component_splits.columns.net_to_owner")}
              </th>
            </tr>
          </thead>
          <tbody className="divide-border divide-y">
            {splits.map((row) => (
              <tr key={row.purpose}>
                <td className="px-4 py-2 font-medium">
                  {purposeLabel(row.purpose)}
                  {row.status === "waived" ? (
                    <span className="text-muted-foreground ml-2 text-xs font-normal italic">
                      {t("finance.component_splits.waived")}
                    </span>
                  ) : null}
                  {row.due_at ? (
                    <div className="text-muted-foreground text-xs font-normal">
                      {/* due_at is stored midnight-UTC; render the UTC day. */}
                      {t("finance.component_splits.due", {
                        date: formatDate(row.due_at.slice(0, 10)),
                      })}
                    </div>
                  ) : null}
                </td>
                <td className="px-4 py-2 text-right tabular-nums">
                  {formatMoney(row.gross, currency)}
                </td>
                <td className="px-4 py-2 text-right tabular-nums">
                  {formatMoney(row.commission, currency)}
                </td>
                <td className="px-4 py-2 text-right tabular-nums">
                  {formatMoney(row.tax, currency)}
                </td>
                <td className="px-4 py-2 text-right tabular-nums">
                  {formatMoney(row.net_to_owner, currency)}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot className="border-border bg-muted/40 border-t">
            <tr>
              <td className="px-4 py-2 font-medium">{t("finance.component_splits.totals")}</td>
              <td className="px-4 py-2 text-right font-medium tabular-nums">
                {formatMoney(totals.gross / 100, currency)}
              </td>
              <td className="px-4 py-2 text-right font-medium tabular-nums">
                {formatMoney(totals.commission / 100, currency)}
              </td>
              <td className="px-4 py-2 text-right font-medium tabular-nums">
                {formatMoney(totals.tax / 100, currency)}
              </td>
              <td className="px-4 py-2 text-right font-medium tabular-nums">
                {formatMoney(totals.net_to_owner / 100, currency)}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
      {netDrifted ? (
        <p className="text-muted-foreground text-sm">{t("finance.component_splits.caveat")}</p>
      ) : null}
    </section>
  );
}

// GAP-086 — the Limitless money-flow lead: who pays what, and what the owner
// keeps. Reads the same owner-money authority (net_to_owner + payment_splits)
// as the GAP-085 Zoho financials block, so res-UI and Zoho can never disagree.
function MoneyFlowSection({
  bookingId,
  netToOwner,
  splits,
  bookingTotal,
  currency,
  bookingCurrency,
  securityFallback,
}: {
  bookingId: number;
  netToOwner: BookingNetToOwner | null | undefined;
  splits: PaymentComponentSplit[] | null | undefined;
  bookingTotal: string | null | undefined;
  currency: string | null;
  /** Booking currency — the SD is guest-side money, so its fallback must not
      route through the owner-money block's currency. */
  bookingCurrency: string | null;
  /** Snapshot `security` figure, pre-formatted — shown when no live SD row. */
  securityFallback: string | null;
}) {
  const { t } = useTranslation("bookings");
  const sd = useSecurityDeposit(bookingId);
  const deposit = sd.data ?? null;

  // Sparse/imported snapshots carry no owner money — fall back to the
  // guest-facing gross; a net figure is never invented.
  const gross = netToOwner?.gross_total ?? bookingTotal;
  const net = netToOwner?.net_to_owner;

  return (
    <section className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="border-border bg-card rounded-lg border px-4 py-3">
          <div className="text-muted-foreground text-sm">{t("finance.money_flow.total_gross")}</div>
          <div className="text-foreground text-lg font-semibold tabular-nums">
            {moneyOrNull(gross, currency) ?? "—"}
          </div>
        </div>
        <div className="border-border bg-card rounded-lg border px-4 py-3">
          <div className="text-muted-foreground text-sm">{t("finance.money_flow.total_net")}</div>
          <div className="text-foreground text-lg font-semibold tabular-nums">
            {moneyOrNull(net, currency) ?? "—"}
          </div>
        </div>
      </div>

      {/* GAP-077: absent (not empty-stated) when null/[] — a schedule-less or
          no-owner-money booking simply has nothing to split. */}
      {splits && splits.length > 0 ? (
        <PaymentSplitSection
          splits={splits}
          netToOwner={netToOwner ?? undefined}
          currency={currency}
        />
      ) : null}

      {/* Security deposit: live SD row wins, snapshot figure is the fallback,
          true absence renders nothing. A failed fetch renders "unavailable" —
          never disguised as absence. Nothing renders while the query is in
          flight, so the fallback can't flash before a live row loads. */}
      {!sd.isLoading && (sd.isError || deposit || securityFallback != null) ? (
        <div className="border-border bg-card flex items-center justify-between gap-3 rounded-lg border px-4 py-3">
          <span className="text-muted-foreground text-sm">
            {t("finance.money_flow.security_deposit")}
          </span>
          {sd.isError ? (
            <span className="text-muted-foreground text-sm">
              {t("finance.money_flow.security_unavailable")}
            </span>
          ) : deposit ? (
            <span className="flex items-center gap-2">
              <span className="text-foreground font-semibold tabular-nums">
                {formatMoney(deposit.amount, deposit.currency_code ?? bookingCurrency)}
              </span>
              <StatusBadge
                status={deposit.status}
                label={securityDepositStatusLabel(deposit.status)}
              />
            </span>
          ) : (
            <span className="text-foreground font-semibold tabular-nums">{securityFallback}</span>
          )}
        </div>
      ) : null}
    </section>
  );
}

export function FinanceTab() {
  const { t } = useTranslation("bookings");
  const { booking } = useOutletContext<BookingOutletContext>();
  const canWrite = useHasReservationsRole();

  const snapshot = useMemo(() => {
    const parsed = parseSnapshot(booking.pricing_snapshot);
    return parsed && snapshotHasContent(parsed) ? parsed : null;
  }, [booking.pricing_snapshot]);
  const currency = booking.currency_code ?? null;

  const charges = useBookingChargeItems(booking.id);
  const deleteMutation = useDeleteChargeItem(booking.id);
  const clearOverride = useSetDepositOverride(booking.id);
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<BookingChargeItem | null>(null);
  const [deleting, setDeleting] = useState<BookingChargeItem | null>(null);
  const [overrideOpen, setOverrideOpen] = useState(false);

  const chargeRows = charges.data?.results ?? [];
  const depositOverride = booking.deposit_override_amount ?? null;

  const handleClearOverride = async () => {
    try {
      await clearOverride.mutateAsync({ amount: null, reason: "" });
      toast.success(t("finance.deposit_override.clear_success"));
    } catch {
      toast.error(t("common:errors.generic"));
    }
  };

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

      <MoneyFlowSection
        bookingId={booking.id}
        netToOwner={booking.net_to_owner}
        splits={booking.payment_splits}
        bookingTotal={booking.total}
        currency={booking.net_to_owner?.currency_code ?? currency}
        bookingCurrency={currency}
        securityFallback={
          snapshot
            ? moneyOrNull(
                pickMoney(snapshot, ["security", "security_deposit"]),
                snapshot.currency_code ?? currency,
              )
            : null
        }
      />

      {/* GAP-087: per-booking deposit override — pin the deposit to a concrete
          figure (e.g. net of a cancellation carry-over credit), or clear it back
          to the property's payment-schedule policy. Writer-gated. */}
      <section className="border-border bg-card flex items-center justify-between gap-3 rounded-lg border px-4 py-3">
        <div className="space-y-0.5">
          <div className="text-foreground text-sm font-medium">
            {t("finance.deposit_override.title")}
          </div>
          <div className="text-muted-foreground text-sm tabular-nums">
            {depositOverride != null
              ? t("finance.deposit_override.active", {
                  amount: formatMoney(depositOverride, currency) ?? depositOverride,
                })
              : t("finance.deposit_override.none")}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {depositOverride != null && canWrite ? (
            <Button
              variant="ghost"
              size="sm"
              className="text-destructive"
              onClick={handleClearOverride}
              disabled={clearOverride.isPending}
            >
              {t("finance.deposit_override.clear")}
            </Button>
          ) : null}
          {canWrite ? (
            <Button size="sm" variant="outline" onClick={() => setOverrideOpen(true)}>
              {depositOverride != null
                ? t("finance.deposit_override.edit")
                : t("finance.deposit_override.set")}
            </Button>
          ) : (
            <Tooltip>
              <TooltipTrigger asChild>
                <span>
                  <Button size="sm" variant="outline" disabled>
                    {t("finance.deposit_override.set")}
                  </Button>
                </span>
              </TooltipTrigger>
              <TooltipContent>{t("finance.charges.role_required_tooltip")}</TooltipContent>
            </Tooltip>
          )}
        </div>
      </section>

      {/* GAP-086: the engine breakdown answers "why is the gross what it is" —
          demoted behind a closed disclosure. No snapshot → the empty state
          renders directly (a disclosure hiding an empty state helps no one). */}
      {snapshot ? (
        <Collapsible
          title={
            <span className="text-foreground text-base font-semibold">
              {t("finance.engine_breakdown")}
            </span>
          }
        >
          <div className="space-y-6 pt-4">
            <SnapshotSection snapshot={snapshot} currency={snapshot.currency_code ?? currency} />
          </div>
        </Collapsible>
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

      {overrideOpen ? (
        <DepositOverrideDialog
          bookingId={booking.id}
          currentAmount={depositOverride}
          open={overrideOpen}
          onOpenChange={setOverrideOpen}
        />
      ) : null}

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
