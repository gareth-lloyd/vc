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
  const { booking } = useOutletContext<BookingOutletContext>();
  const currency = booking.currency_code ?? null;
  const nights = booking.night_count ?? null;

  return (
    <div className="space-y-8 p-6">
      <Section title="Status & key dates">
        <FactList>
          <FactRow
            label="Reference"
            value={<span className="font-mono">{booking.reference}</span>}
          />
          <FactRow label="Status" value={<StatusBadge status={booking.status} />} />
          <FactRow label="Check-in" value={formatDate(booking.date_from)} />
          <FactRow label="Check-out" value={formatDate(booking.date_to)} />
          <FactRow label="Nights" value={nights != null ? nights : "—"} />
          <FactRow
            label="Party"
            value={`${booking.adults} adult${booking.adults === 1 ? "" : "s"}${
              booking.children
                ? `, ${booking.children} child${booking.children === 1 ? "" : "ren"}`
                : ""
            }`}
          />
        </FactList>
      </Section>

      <Section title="Guest & property">
        <FactList>
          <FactRow
            label="Guest"
            value={
              booking.guest_name ?? (
                <span className="text-muted-foreground">{`Guest #${booking.guest}`}</span>
              )
            }
          />
          <FactRow
            label="Guest email"
            value={booking.guest_email ?? <span className="text-muted-foreground">—</span>}
          />
          <FactRow
            label="Property"
            value={
              booking.property_name ?? (
                <span className="text-muted-foreground">{`Property #${booking.property}`}</span>
              )
            }
          />
          <FactRow
            label="Source"
            value={<span className="capitalize">{booking.site_source.replace(/_/g, " ")}</span>}
          />
        </FactList>
      </Section>

      <Section title="Financial summary">
        <FactList>
          <FactRow label="Rental price" value={formatMoney(booking.rental_price, currency)} />
          <FactRow label="Discount" value={formatMoney(booking.discount ?? "0", currency)} />
          <FactRow label="Adjustment" value={formatMoney(booking.adjustment ?? "0", currency)} />
          <FactRow label="Balance due" value={formatMoney(booking.balance_due, currency)} />
          <FactRow label="Balance due by" value={formatDate(booking.balance_due_at)} />
        </FactList>
      </Section>
    </div>
  );
}
