import { NavLink, Outlet, useParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { TwoColumn } from "@/components/layout/TwoColumn";
import { StatusBadge } from "@/components/data/StatusBadge";
import { FactList, FactRow } from "@/components/data/FactList";
import { ErrorState } from "@/components/feedback/ErrorState";
import { QuickActions, type QuickAction } from "@/components/feedback/QuickActions";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/format/date";
import { formatMoney, parseMoney } from "@/lib/format/money";
import { useBooking } from "./hooks";
import type { BookingDetail } from "./schemas";

export const BOOKING_TABS = [
  { slug: "overview", label: "Overview" },
  { slug: "timeline", label: "Timeline" },
  { slug: "finance", label: "Finance" },
  { slug: "payments", label: "Payments" },
  { slug: "concierge", label: "Concierge" },
  { slug: "owner", label: "Owner" },
] as const;

const QUICK_ACTIONS: readonly QuickAction[] = [
  { label: "Send to guest" },
  { label: "Send to owner" },
  { label: "Cancel booking" },
];

function RailSummary({ booking }: { booking: BookingDetail }) {
  const currency = booking.currency_code ?? null;
  const total = booking.total ?? booking.rental_price;
  const paid = parseMoney(total) - parseMoney(booking.balance_due);
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-foreground text-lg font-semibold">{booking.reference}</h2>
        <p className="text-muted-foreground text-sm">
          {booking.property_name ?? `Property #${booking.property}`}
        </p>
      </div>
      <StatusBadge status={booking.status} />
      <FactList>
        <FactRow
          label="Dates"
          value={`${formatDate(booking.date_from)} – ${formatDate(booking.date_to)}`}
        />
        <FactRow label="Guest" value={booking.guest_name ?? `Guest #${booking.guest}`} />
        <FactRow label="Total" value={formatMoney(total, currency)} />
        <FactRow label="Paid" value={Number.isFinite(paid) ? formatMoney(paid, currency) : "—"} />
        <FactRow label="Due" value={formatMoney(booking.balance_due, currency)} />
      </FactList>
      <QuickActions actions={QUICK_ACTIONS} />
    </div>
  );
}

export interface BookingOutletContext {
  booking: BookingDetail;
}

export function BookingDetailLayout() {
  const { id } = useParams<{ id: string }>();
  const query = useBooking(id);

  if (query.isLoading) {
    return (
      <div className="space-y-4 p-6">
        <Skeleton className="h-8 w-1/3" />
        <Skeleton className="h-4 w-1/4" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (query.isError || !query.data) {
    return (
      <div className="p-6">
        <ErrorState
          title="Couldn't load this booking"
          description="Try again or head back to the list."
          onRetry={() => query.refetch()}
        />
      </div>
    );
  }

  const booking = query.data;

  return (
    <div>
      <PageHeader
        title={booking.reference}
        subtitle={booking.property_name ?? undefined}
        breadcrumbs={[{ label: "Bookings", to: "/bookings" }, { label: booking.reference }]}
      />

      <div className="border-border border-b px-6">
        <nav className="flex gap-1" aria-label="Booking sections">
          {BOOKING_TABS.map((tab) => (
            <NavLink
              key={tab.slug}
              to={tab.slug}
              className={({ isActive }) =>
                cn(
                  "border-b-2 px-3 py-2 text-sm font-medium",
                  isActive
                    ? "border-foreground text-foreground"
                    : "text-muted-foreground hover:text-foreground border-transparent",
                )
              }
            >
              {tab.label}
            </NavLink>
          ))}
        </nav>
      </div>

      <TwoColumn rightRail={<RailSummary booking={booking} />}>
        <Outlet context={{ booking } satisfies BookingOutletContext} />
      </TwoColumn>
    </div>
  );
}
