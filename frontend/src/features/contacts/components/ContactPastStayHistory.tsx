import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Collapsible } from "@/components/ui/collapsible";
import { importedBookingWhen, recordedAmount } from "@/lib/domain/importedBooking";
import type { ContactId } from "@/lib/query/keys";
import { useContactPastStays } from "../hooks";

interface ContactPastStayHistoryProps {
  contactId: ContactId;
}

/**
 * UI name: "Imported bookings" (GAP-117) — PastStay rows from the legacy
 * cutover import only; the /bookings tab lists the same rows across clients.
 *
 * GAP-089: the customer's historic stays from Nick's spreadsheets — a year,
 * a villa name and a legacy booking number — as PastStay rows rather than
 * Bookings, in their own accordion beside ContactBookingHistory. Same shape as
 * that component: collapsed by default, count badge loads on mount, rows
 * revealed on expand. GAP-113: stays the legacy archive re-keyed also carry
 * exact dates (shown instead of the year) and the amount as recorded.
 */
export function ContactPastStayHistory({ contactId }: ContactPastStayHistoryProps) {
  const { t } = useTranslation("contacts");
  const query = useContactPastStays(contactId);

  const rows = query.data?.results ?? [];
  const total = query.data?.count ?? 0;
  const hiddenCount = query.data?.next ? total - rows.length : 0;

  return (
    <Collapsible
      className="rounded-md border"
      headerClassName="px-3 py-2 text-sm font-medium"
      toggleAriaLabel={t("profile.stays_toggle_aria")}
      title={
        <span>
          {total > 0 ? `${t("profile.stays_title")} (${total})` : t("profile.stays_title")}
        </span>
      }
    >
      <div className="border-border border-t">
        {query.isLoading ? (
          <p className="text-muted-foreground px-3 py-2 text-sm">{t("profile.stays_loading")}</p>
        ) : query.isError ? (
          <p className="text-destructive px-3 py-2 text-sm">{t("profile.stays_error")}</p>
        ) : rows.length === 0 ? (
          <p className="text-muted-foreground px-3 py-2 text-sm">{t("profile.stays_empty")}</p>
        ) : (
          <ul className="divide-border divide-y">
            {rows.map((row) => {
              const amount = recordedAmount(row);
              return (
                <li
                  key={row.id}
                  className="flex items-center justify-between gap-2 px-3 py-2 text-sm"
                >
                  <div className="flex min-w-0 items-center gap-2">
                    {row.property != null ? (
                      <Link
                        to={`/properties/${row.property}`}
                        className="hover:text-primary truncate font-medium hover:underline"
                      >
                        {row.property_name ?? row.villa_name}
                      </Link>
                    ) : (
                      <span className="truncate font-medium">{row.villa_name}</span>
                    )}
                    {row.destination ? (
                      <span className="text-muted-foreground truncate text-xs">
                        {row.destination}
                      </span>
                    ) : null}
                  </div>
                  <div className="text-muted-foreground flex shrink-0 flex-col items-end text-xs">
                    <span>
                      {importedBookingWhen(row) ?? t("profile.stays_year_unknown")}
                      {row.booking_number ? ` · ${row.booking_number}` : ""}
                    </span>
                    {amount ? (
                      <span>{t("profile.stays_amount_as_recorded", { amount })}</span>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
        {hiddenCount > 0 ? (
          <p className="text-muted-foreground px-3 py-2 text-xs">
            {t("profile.stays_more", { count: hiddenCount })}
          </p>
        ) : null}
      </div>
    </Collapsible>
  );
}
