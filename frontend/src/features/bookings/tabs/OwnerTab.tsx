import { Link, useOutletContext } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { FactList, FactRow } from "@/components/data/FactList";
import { Section } from "@/components/data/Section";
import { EmptyState } from "@/components/feedback/EmptyState";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { formatMoney, parseMoney } from "@/lib/format/money";
import { pricingSnapshotSchema } from "../schemas";
import type { BookingOutletContext } from "../BookingDetailLayout";

export function OwnerTab() {
  const { t } = useTranslation("bookings");
  const { booking } = useOutletContext<BookingOutletContext>();
  const owner = booking.owner ?? null;
  const commission = booking.commission ?? null;
  const currency = booking.currency_code ?? null;
  const snapshotParse = pricingSnapshotSchema.safeParse(booking.pricing_snapshot ?? {});
  if (!snapshotParse.success && import.meta.env.DEV) {
    console.warn("OwnerTab: pricing_snapshot failed to parse", snapshotParse.error);
  }
  const snapshot = snapshotParse.data ?? null;

  return (
    <div className="space-y-6 p-6">
      <Section title={t("owner.title")}>
        {owner === null ? (
          <EmptyState
            title={t(commission === null ? "owner.empty.no_finance" : "owner.empty.no_contact")}
          />
        ) : (
          <div className="space-y-3">
            <FactList>
              <FactRow
                label={t("owner.fields.name")}
                value={`${owner.first_name} ${owner.last_name}`.trim() || "—"}
              />
              {owner.company && <FactRow label={t("owner.fields.company")} value={owner.company} />}
              {owner.primary_email && (
                <FactRow
                  label={t("owner.fields.email")}
                  value={
                    <a className="hover:underline" href={`mailto:${owner.primary_email}`}>
                      {owner.primary_email}
                    </a>
                  }
                />
              )}
              {owner.primary_phone && (
                <FactRow
                  label={t("owner.fields.phone")}
                  value={
                    <a className="hover:underline" href={`tel:${owner.primary_phone}`}>
                      {owner.primary_phone}
                    </a>
                  }
                />
              )}
              {(owner.address_line_1 || owner.address_line_2) && (
                <FactRow
                  label={t("owner.fields.address")}
                  value={[owner.address_line_1, owner.address_line_2].filter(Boolean).join(", ")}
                />
              )}
            </FactList>
            <Link
              to={`/contacts/${owner.id}`}
              className={cn(buttonVariants({ variant: "outline", size: "sm" }))}
            >
              {t("owner.actions.view_contact")}
            </Link>
          </div>
        )}
      </Section>

      {/* Payout terms are operator context for paying *this* owner — without an
          owner contact, they have nothing to attach to. Suppress the section
          rather than displaying inherited commission terms in a vacuum. */}
      {owner !== null && (
        <Section title={t("owner.payout_title")}>
          <CommissionBlock commission={commission} currency={currency} t={t} />
          <SnapshotBlock snapshot={snapshot} currency={currency} t={t} />
        </Section>
      )}
    </div>
  );
}

type TFn = ReturnType<typeof useTranslation<"bookings">>["t"];

function CommissionBlock({
  commission,
  currency,
  t,
}: {
  commission: BookingOutletContext["booking"]["commission"] | null;
  currency: string | null;
  t: TFn;
}) {
  const hasAmount = !!commission && commission.amount != null;
  const hasNote = !!commission && !!commission.note;
  const hasKind = !!commission && commission.calculation_type !== null;
  if (!commission || (!hasAmount && !hasNote && !hasKind)) {
    return <EmptyState title={t("owner.empty.no_commission_terms")} />;
  }
  const kindLabel = hasKind ? t(`owner.commission.kind.${commission.calculation_type!}`) : null;
  const amountLabel = !hasAmount
    ? null
    : commission.calculation_type === "percent"
      ? `${Number(commission.amount).toFixed(2)}%`
      : formatMoney(commission.amount, currency);
  const valueParts = [kindLabel, amountLabel].filter(Boolean) as string[];
  return (
    <FactList>
      {valueParts.length > 0 && (
        <FactRow label={t("owner.commission.label")} value={valueParts.join(" · ")} />
      )}
      {commission.note && (
        <FactRow label={t("owner.commission.note_label")} value={commission.note} />
      )}
    </FactList>
  );
}

function formatComponent(raw: string | number, code: string | null): string {
  if (code) return formatMoney(raw, code);
  // No currency available — render the raw decimal so the row still carries
  // information instead of disappearing behind a blanket "—".
  const amount = parseMoney(raw);
  if (!Number.isFinite(amount)) return String(raw);
  return amount.toLocaleString("en-GB", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function SnapshotBlock({
  snapshot,
  currency,
  t,
}: {
  snapshot: ReturnType<typeof pricingSnapshotSchema.safeParse>["data"] | null;
  currency: string | null;
  t: TFn;
}) {
  if (!snapshot) return null;
  const code = snapshot.currency_code ?? currency;
  const rows: Array<[string, unknown]> = [
    [t("owner.payout.fields.rate_subtotal"), snapshot.rate_subtotal],
    [t("owner.payout.fields.extras_total"), snapshot.extras_total],
    [t("owner.payout.fields.discount"), snapshot.discount],
    [t("owner.payout.fields.commission"), snapshot.commission],
    [t("owner.payout.fields.tax"), snapshot.tax ?? snapshot.taxes],
    [t("owner.payout.fields.total"), snapshot.grand_total ?? snapshot.total],
  ];
  const visible = rows.flatMap(([label, raw]) => {
    if (raw == null || raw === "") return [];
    return [{ label, value: formatComponent(raw as string | number, code) }];
  });
  if (visible.length === 0) return null;
  return (
    <section className="mt-4 space-y-2">
      <h3 className="text-foreground text-sm font-semibold">
        {t("owner.payout.components_heading")}
      </h3>
      <FactList>
        {visible.map((row) => (
          <FactRow key={row.label} label={row.label} value={row.value} />
        ))}
      </FactList>
    </section>
  );
}
