import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { StatusBadge } from "@/components/data/StatusBadge";
import { Collapsible } from "@/components/ui/collapsible";
import { bookingStatusLabel } from "@/features/bookings/schemas";
import { enquiryStatusLabel } from "@/features/enquiries/schemas";
import type { ContactId } from "@/lib/query/keys";
import { useContactEnquiries } from "../hooks";

interface ContactEnquiryHistoryProps {
  contactId: ContactId;
}

export function ContactEnquiryHistory({ contactId }: ContactEnquiryHistoryProps) {
  const { t } = useTranslation("contacts");
  const query = useContactEnquiries(contactId);

  const rows = query.data?.results ?? [];
  const total = query.data?.count ?? 0;
  // DRF-paginated: `next` signals there are more rows than this first page.
  const hiddenCount = query.data?.next ? total - rows.length : 0;

  // Collapsed by default — the panel is a glanceable aside, not the focus.
  return (
    <Collapsible
      className="rounded-md border"
      headerClassName="px-3 py-2 text-sm font-medium"
      toggleAriaLabel={t("history.toggle_aria")}
      title={<span>{total > 0 ? `${t("history.title")} (${total})` : t("history.title")}</span>}
    >
      <div className="border-border border-t">
        {query.isLoading ? (
          <p className="text-muted-foreground px-3 py-2 text-sm">{t("history.loading")}</p>
        ) : query.isError ? (
          <p className="text-destructive px-3 py-2 text-sm">{t("history.error")}</p>
        ) : rows.length === 0 ? (
          <p className="text-muted-foreground px-3 py-2 text-sm">{t("history.empty")}</p>
        ) : (
          <ul className="divide-border divide-y">
            {rows.map((row) => (
              <li
                key={row.id}
                className="flex items-center justify-between gap-2 px-3 py-2 text-sm"
              >
                <div className="flex min-w-0 items-center gap-2">
                  <Link
                    to={`/enquiries/${row.id}`}
                    className="hover:text-primary truncate font-medium hover:underline"
                  >
                    {row.reference}
                  </Link>
                  <StatusBadge status={enquiryStatusLabel(row.status)} />
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <span className="text-muted-foreground text-xs">
                    {t("history.quote_count", { count: row.quote_count })}
                  </span>
                  {row.converted_booking ? (
                    <span className="flex items-center gap-1">
                      <Link
                        to={`/bookings/${row.converted_booking.id}/overview`}
                        className="text-muted-foreground hover:text-primary text-xs hover:underline"
                      >
                        {row.converted_booking.reference}
                      </Link>
                      <StatusBadge status={bookingStatusLabel(row.converted_booking.status)} />
                    </span>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}
        {hiddenCount > 0 ? (
          <p className="text-muted-foreground px-3 py-2 text-xs">
            {t("history.more", { count: hiddenCount })}
          </p>
        ) : null}
      </div>
    </Collapsible>
  );
}
