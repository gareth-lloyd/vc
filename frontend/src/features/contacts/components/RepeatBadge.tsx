import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";

interface RepeatBadgeProps {
  /** Total bookings the customer holds (property-agnostic). */
  bookingCount: number;
  /**
   * GAP-089: historic stays imported from the spreadsheets (no Booking row).
   * Shown as its own "{n} past stays" figure so a live booking is never
   * conflated with a sheet-only record.
   */
  pastStayCount?: number;
  /** Whether the customer counts as a returning client (>= 1 booking or past stay). */
  isRepeat: boolean;
}

/**
 * GAP-042: the at-a-glance "Repeat" flag for the customer-360 profile. Renders a
 * "Repeat" badge plus the booking count when the customer has booked before;
 * renders nothing for a first-time contact so the rail stays uncluttered.
 */
export function RepeatBadge({ bookingCount, pastStayCount = 0, isRepeat }: RepeatBadgeProps) {
  const { t } = useTranslation("contacts");
  if (!isRepeat) return null;
  const parts: string[] = [];
  if (bookingCount > 0 || pastStayCount === 0) {
    parts.push(t("profile.booking_count", { count: bookingCount }));
  }
  if (pastStayCount > 0) {
    parts.push(t("profile.stay_count", { count: pastStayCount }));
  }
  return (
    <span className="flex items-center gap-2">
      <Badge variant="secondary">{t("profile.repeat")}</Badge>
      <span className="text-muted-foreground text-xs">{parts.join(" · ")}</span>
    </span>
  );
}
