import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronRight } from "lucide-react";
import { StatusBadge } from "@/components/data/StatusBadge";
import { cn } from "@/lib/cn";
import { bookingStatusLabel } from "@/features/bookings/schemas";
import { enquiryStatusLabel } from "@/features/enquiries/schemas";
import type { GuestId } from "@/lib/query/keys";
import { useGuestEnquiries } from "../hooks";

interface GuestEnquiryHistoryProps {
  guestId: GuestId;
}

export function GuestEnquiryHistory({ guestId }: GuestEnquiryHistoryProps) {
  const { t } = useTranslation("guests");
  // Collapsed by default — the panel is a glanceable aside, not the focus.
  const [open, setOpen] = useState(false);
  const query = useGuestEnquiries(guestId);

  const rows = query.data?.results ?? [];
  const total = query.data?.count ?? 0;
  // DRF-paginated: `next` signals there are more rows than this first page.
  const hiddenCount = query.data?.next ? total - rows.length : 0;

  return (
    <div className="rounded-md border">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label={t("history.toggle_aria")}
        className="flex w-full items-center justify-between px-3 py-2 text-sm font-medium"
      >
        <span>{total > 0 ? `${t("history.title")} (${total})` : t("history.title")}</span>
        <ChevronRight className={cn("size-4 transition-transform", open && "rotate-90")} />
      </button>

      {open ? (
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
                    <span className="truncate font-medium">{row.reference}</span>
                    <StatusBadge status={enquiryStatusLabel(row.status)} />
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className="text-muted-foreground text-xs">
                      {t("history.quote_count", { count: row.quote_count })}
                    </span>
                    {row.converted_booking ? (
                      <span className="flex items-center gap-1">
                        <span className="text-muted-foreground text-xs">
                          {row.converted_booking.reference}
                        </span>
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
      ) : null}
    </div>
  );
}
