import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { formatDate } from "@/lib/format/date";
import { enquirySourceLabel, type EnquiryListItem } from "../schemas";

interface EnquiryCardProps {
  enquiry: EnquiryListItem;
  onClick?: () => void;
}

export function EnquiryCard({ enquiry, onClick }: EnquiryCardProps) {
  const { t } = useTranslation("enquiries");

  // Prefer server-resolved guest_name (walks the Guest FK) and fall back to the
  // denormalised first/last/email captured at lead time for anonymous submissions.
  const denormName = `${enquiry.first_name ?? ""} ${enquiry.last_name ?? ""}`.trim();
  const title = enquiry.guest_name || denormName || enquiry.email || t("card.unknown_guest");

  const dateRange =
    !enquiry.date_from && !enquiry.date_to
      ? t("card.flexible_dates")
      : `${formatDate(enquiry.date_from ?? null)} – ${formatDate(enquiry.date_to ?? null)}`;

  const propertyText =
    enquiry.property_name ??
    (enquiry.property != null
      ? t("card.property_with_id", { id: enquiry.property })
      : t("card.no_property"));

  const timeAgo = (iso: string | null | undefined): string => {
    if (!iso) return "";
    const then = new Date(iso).getTime();
    if (!Number.isFinite(then)) return "";
    const diffMs = Date.now() - then;
    const minutes = Math.floor(diffMs / 60_000);
    if (minutes < 1) return t("card.time_ago.just_now");
    if (minutes < 60) return t("card.time_ago.minutes", { count: minutes });
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return t("card.time_ago.hours", { count: hours });
    const days = Math.floor(hours / 24);
    if (days < 30) return t("card.time_ago.days", { count: days });
    return formatDate(iso);
  };

  return (
    <button
      type="button"
      onClick={onClick}
      className="border-border bg-card hover:bg-accent/40 shadow-card w-full space-y-2 rounded-md border p-3 text-left text-sm transition-colors"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="text-foreground font-medium">{title}</div>
        <span className="text-muted-foreground font-mono text-xs">{enquiry.reference}</span>
      </div>
      <div className="text-foreground text-xs">{propertyText}</div>
      <div className="text-muted-foreground text-xs">{dateRange}</div>
      <div className="flex items-center justify-between gap-2">
        <Badge variant="outline" className="text-xs">
          {enquirySourceLabel(enquiry.site_source)}
        </Badge>
        <span className="text-muted-foreground text-xs">{timeAgo(enquiry.created_at)}</span>
      </div>
    </button>
  );
}
