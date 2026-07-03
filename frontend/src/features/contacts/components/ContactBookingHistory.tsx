import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { StatusBadge } from "@/components/data/StatusBadge";
import { Collapsible } from "@/components/ui/collapsible";
import { formatDate } from "@/lib/format/date";
import { bookingStatusLabel } from "@/features/bookings/schemas";
import type { ContactId } from "@/lib/query/keys";
import { useContactBookings } from "../hooks";

interface ContactBookingHistoryProps {
  contactId: ContactId;
}

/**
 * GAP-042: the customer's previous-bookings aside on the 360 profile — the
 * legacy "GetPreviousBooking" grid, now over the unified Person. Mirrors
 * ContactEnquiryHistory: a glanceable, collapsed-by-default accordion whose
 * count badge loads on mount (the row list is revealed on expand).
 */
export function ContactBookingHistory({ contactId }: ContactBookingHistoryProps) {
  const { t } = useTranslation("contacts");
  const query = useContactBookings(contactId);

  const rows = query.data?.results ?? [];
  const total = query.data?.count ?? 0;
  const hiddenCount = query.data?.next ? total - rows.length : 0;

  return (
    <Collapsible
      className="rounded-md border"
      headerClassName="px-3 py-2 text-sm font-medium"
      toggleAriaLabel={t("profile.bookings_toggle_aria")}
      title={
        <span>
          {total > 0 ? `${t("profile.bookings_title")} (${total})` : t("profile.bookings_title")}
        </span>
      }
    >
      <div className="border-border border-t">
        {query.isLoading ? (
          <p className="text-muted-foreground px-3 py-2 text-sm">{t("profile.bookings_loading")}</p>
        ) : query.isError ? (
          <p className="text-destructive px-3 py-2 text-sm">{t("profile.bookings_error")}</p>
        ) : rows.length === 0 ? (
          <p className="text-muted-foreground px-3 py-2 text-sm">{t("profile.bookings_empty")}</p>
        ) : (
          <ul className="divide-border divide-y">
            {rows.map((row) => (
              <li
                key={row.id}
                className="flex items-center justify-between gap-2 px-3 py-2 text-sm"
              >
                <div className="flex min-w-0 items-center gap-2">
                  <Link
                    to={`/bookings/${row.id}/overview`}
                    className="hover:text-primary truncate font-medium hover:underline"
                  >
                    {row.reference}
                  </Link>
                  <StatusBadge status={bookingStatusLabel(row.status)} />
                </div>
                <span className="text-muted-foreground shrink-0 text-xs">
                  {formatDate(row.date_from)} – {formatDate(row.date_to)}
                </span>
              </li>
            ))}
          </ul>
        )}
        {hiddenCount > 0 ? (
          <p className="text-muted-foreground px-3 py-2 text-xs">
            {t("profile.bookings_more", { count: hiddenCount })}
          </p>
        ) : null}
      </div>
    </Collapsible>
  );
}
