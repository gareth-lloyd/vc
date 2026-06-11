import { useTranslation } from "react-i18next";
import { Link, useOutletContext } from "react-router-dom";
import { StatusBadge } from "@/components/data/StatusBadge";
import { FactGrid, FactGridItem } from "@/components/data/FactGrid";
import { StatTiles, type StatTileData } from "@/components/data/StatTiles";
import { formatDate } from "@/lib/format/date";
import { propertyDetailsPath } from "@/lib/routes";
import { formatMoney } from "@/lib/format/money";
import { bookingFinance, dueTone } from "../finance";
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

  const { total, paid, due } = bookingFinance(booking);
  const tiles: StatTileData[] = [
    { label: t("detail.rail.total"), value: formatMoney(total, currency) },
    {
      label: t("detail.rail.paid"),
      value: formatMoney(paid, currency),
      tone: "success",
    },
    {
      label: t("detail.rail.due"),
      value: formatMoney(due, currency),
      tone: dueTone(due, booking.balance_due_at),
      hint: booking.balance_due_at ? formatDate(booking.balance_due_at) : undefined,
    },
    { label: t("overview.fields.nights"), value: nights != null ? nights : "—" },
  ];

  return (
    <div className="space-y-8 p-6">
      <StatTiles tiles={tiles} />

      <Section title={t("overview.sections.status_and_dates")}>
        <FactGrid>
          <FactGridItem
            label={t("overview.fields.reference")}
            value={<span className="font-mono">{booking.reference}</span>}
          />
          <FactGridItem
            label={t("overview.fields.status")}
            value={<StatusBadge status={booking.status} />}
          />
          <FactGridItem
            label={t("overview.fields.check_in")}
            value={formatDate(booking.date_from)}
          />
          <FactGridItem
            label={t("overview.fields.check_out")}
            value={formatDate(booking.date_to)}
          />
          <FactGridItem label={t("overview.fields.party")} value={partyValue} />
        </FactGrid>
      </Section>

      <Section title={t("overview.sections.guest_and_property")}>
        <FactGrid>
          {/* booking.guest is a reservations.Guest id, not a Contact id — no
              Guests page exists yet, so the name renders unlinked. */}
          <FactGridItem
            label={t("overview.fields.guest")}
            value={
              booking.guest_name ?? (
                <span className="text-muted-foreground">
                  {t("detail.fallback.guest_with_id", { id: booking.guest })}
                </span>
              )
            }
          />
          <FactGridItem
            label={t("overview.fields.guest_email")}
            value={booking.guest_email ?? <span className="text-muted-foreground">—</span>}
          />
          <FactGridItem
            label={t("overview.fields.property")}
            value={
              <Link to={propertyDetailsPath(booking.property)} className="hover:underline">
                {booking.property_name ?? (
                  <span className="text-muted-foreground">
                    {t("detail.fallback.property_with_id", { id: booking.property })}
                  </span>
                )}
              </Link>
            }
          />
          <FactGridItem
            label={t("overview.fields.source")}
            value={<span className="capitalize">{sourceLabel}</span>}
          />
        </FactGrid>
      </Section>

      <Section title={t("overview.sections.financial_summary")}>
        <FactGrid>
          <FactGridItem
            label={t("overview.fields.rental_price")}
            value={formatMoney(booking.rental_price, currency)}
          />
          <FactGridItem
            label={t("overview.fields.discount")}
            value={formatMoney(booking.discount ?? "0", currency)}
          />
          <FactGridItem
            label={t("overview.fields.adjustment")}
            value={formatMoney(booking.adjustment ?? "0", currency)}
          />
          {booking.net_to_owner ? (
            <FactGridItem
              label={t("overview.fields.commission")}
              value={formatMoney(booking.net_to_owner.commission, currency)}
            />
          ) : null}
          <FactGridItem label={t("overview.fields.total")} value={formatMoney(total, currency)} />
        </FactGrid>
      </Section>
    </div>
  );
}
