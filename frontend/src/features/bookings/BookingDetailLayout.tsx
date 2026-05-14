import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { TwoColumn } from "@/components/layout/TwoColumn";
import { StatusBadge } from "@/components/data/StatusBadge";
import { FactList, FactRow } from "@/components/data/FactList";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/format/date";
import { formatMoney, parseMoney } from "@/lib/format/money";
import { useBooking } from "./hooks";
import { BookingActions } from "./components/BookingActions";
import type { BookingDetail } from "./schemas";

export const BOOKING_TABS = [
  { slug: "overview", labelKey: "tabs.overview" },
  { slug: "timeline", labelKey: "tabs.timeline" },
  { slug: "notes", labelKey: "tabs.notes" },
  { slug: "finance", labelKey: "tabs.finance" },
  { slug: "payments", labelKey: "tabs.payments" },
  { slug: "concierge", labelKey: "tabs.concierge" },
  { slug: "owner", labelKey: "tabs.owner" },
] as const;

function RailSummary({ booking }: { booking: BookingDetail }) {
  const { t } = useTranslation("bookings");
  const currency = booking.currency_code ?? null;
  const total = booking.total ?? booking.rental_price;
  const paid = parseMoney(total) - parseMoney(booking.balance_due);
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-foreground text-lg font-semibold">{booking.reference}</h2>
        <p className="text-muted-foreground text-sm">
          {booking.property_name ?? t("detail.fallback.property_with_id", { id: booking.property })}
        </p>
      </div>
      <StatusBadge status={booking.status} />
      <FactList>
        <FactRow
          label={t("detail.rail.dates")}
          value={`${formatDate(booking.date_from)} – ${formatDate(booking.date_to)}`}
        />
        <FactRow
          label={t("detail.rail.guest")}
          value={booking.guest_name ?? t("detail.fallback.guest_with_id", { id: booking.guest })}
        />
        <FactRow label={t("detail.rail.total")} value={formatMoney(total, currency)} />
        <FactRow
          label={t("detail.rail.paid")}
          value={Number.isFinite(paid) ? formatMoney(paid, currency) : "—"}
        />
        <FactRow label={t("detail.rail.due")} value={formatMoney(booking.balance_due, currency)} />
      </FactList>
      <BookingActions booking={booking} />
    </div>
  );
}

export interface BookingOutletContext {
  booking: BookingDetail;
}

export function BookingDetailLayout() {
  const { t } = useTranslation("bookings");
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
          title={t("detail.load_failed_title")}
          description={t("detail.load_failed_body")}
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
        breadcrumbs={[
          { label: t("detail.breadcrumb_list"), to: "/bookings" },
          { label: booking.reference },
        ]}
      />

      <div className="border-border border-b px-6">
        <nav className="flex gap-1" aria-label={t("detail.sections_aria")}>
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
              {t(tab.labelKey)}
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
