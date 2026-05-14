import { useTranslation } from "react-i18next";
import { useOutletContext } from "react-router-dom";
import { StatusBadge } from "@/components/data/StatusBadge";
import { FactList, FactRow } from "@/components/data/FactList";
import { formatDate } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/money";
import type { BookingOutletContext } from "../BookingDetailLayout";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="text-foreground text-base font-semibold">{title}</h2>
      {children}
    </section>
  );
}

export function OverviewTab() {
  const { t } = useTranslation("bookings");
  const { booking } = useOutletContext<BookingOutletContext>();
  const currency = booking.currency_code ?? null;
  const nights = booking.night_count ?? null;

  const adultsPart = t("overview.party_format.adults", { count: booking.adults });
  const childrenPart = booking.children
    ? t("overview.party_format.children", { count: booking.children })
    : "";
  const partyValue = `${adultsPart}${childrenPart}`;

  // site_source is a backend-controlled string. Resolve known values via the
  // bookings:source.* namespace; unknown values fall through with whitespace
  // normalisation so we never blank out a value we don't yet have a key for.
  const sourceLabel = (() => {
    const key = booking.site_source.replace(/[^a-z0-9_]/gi, "_").toLowerCase();
    const resolved = t(`source.${key}`, { defaultValue: "" });
    return resolved || booking.site_source.replace(/_/g, " ");
  })();

  return (
    <div className="space-y-8 p-6">
      <Section title={t("overview.sections.status_and_dates")}>
        <FactList>
          <FactRow
            label={t("overview.fields.reference")}
            value={<span className="font-mono">{booking.reference}</span>}
          />
          <FactRow
            label={t("overview.fields.status")}
            value={<StatusBadge status={booking.status} />}
          />
          <FactRow label={t("overview.fields.check_in")} value={formatDate(booking.date_from)} />
          <FactRow label={t("overview.fields.check_out")} value={formatDate(booking.date_to)} />
          <FactRow label={t("overview.fields.nights")} value={nights != null ? nights : "—"} />
          <FactRow label={t("overview.fields.party")} value={partyValue} />
        </FactList>
      </Section>

      <Section title={t("overview.sections.guest_and_property")}>
        <FactList>
          <FactRow
            label={t("overview.fields.guest")}
            value={
              booking.guest_name ?? (
                <span className="text-muted-foreground">
                  {t("detail.fallback.guest_with_id", { id: booking.guest })}
                </span>
              )
            }
          />
          <FactRow
            label={t("overview.fields.guest_email")}
            value={booking.guest_email ?? <span className="text-muted-foreground">—</span>}
          />
          <FactRow
            label={t("overview.fields.property")}
            value={
              booking.property_name ?? (
                <span className="text-muted-foreground">
                  {t("detail.fallback.property_with_id", { id: booking.property })}
                </span>
              )
            }
          />
          <FactRow
            label={t("overview.fields.source")}
            value={<span className="capitalize">{sourceLabel}</span>}
          />
        </FactList>
      </Section>

      <Section title={t("overview.sections.financial_summary")}>
        <FactList>
          <FactRow
            label={t("overview.fields.rental_price")}
            value={formatMoney(booking.rental_price, currency)}
          />
          <FactRow
            label={t("overview.fields.discount")}
            value={formatMoney(booking.discount ?? "0", currency)}
          />
          <FactRow
            label={t("overview.fields.adjustment")}
            value={formatMoney(booking.adjustment ?? "0", currency)}
          />
          <FactRow
            label={t("overview.fields.balance_due")}
            value={formatMoney(booking.balance_due, currency)}
          />
          <FactRow
            label={t("overview.fields.balance_due_by")}
            value={formatDate(booking.balance_due_at)}
          />
        </FactList>
      </Section>
    </div>
  );
}
