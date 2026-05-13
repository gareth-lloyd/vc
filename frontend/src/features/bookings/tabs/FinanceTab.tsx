import { useMemo } from "react";
import { useOutletContext } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { FactList, FactRow } from "@/components/data/FactList";
import { EmptyState } from "@/components/feedback/EmptyState";
import { formatDate } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/money";
import { pricingSnapshotSchema, type PricingSnapshot, type PricingSnapshotLine } from "../schemas";
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

export function FinanceTab() {
  const { t } = useTranslation("bookings");
  const { booking } = useOutletContext<BookingOutletContext>();

  const snapshot = useMemo(
    () => parseSnapshot(booking.pricing_snapshot),
    [booking.pricing_snapshot],
  );

  if (!snapshot) {
    return (
      <div className="p-6">
        <EmptyState title={t("finance.empty.title")} description={t("finance.empty.description")} />
      </div>
    );
  }

  const currency = snapshot.currency_code ?? booking.currency_code ?? null;

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
    <div className="space-y-6 p-6">
      <h2 className="text-foreground text-lg font-semibold">{t("finance.title")}</h2>
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
    </div>
  );
}
