import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";

interface RepeatBadgeProps {
  /** Total bookings the customer holds (property-agnostic). */
  bookingCount: number;
  /** Whether the customer counts as a returning client (>= 1 booking). */
  isRepeat: boolean;
}

/**
 * GAP-042: the at-a-glance "Repeat" flag for the customer-360 profile. Renders a
 * "Repeat" badge plus the booking count when the customer has booked before;
 * renders nothing for a first-time contact so the rail stays uncluttered.
 */
export function RepeatBadge({ bookingCount, isRepeat }: RepeatBadgeProps) {
  const { t } = useTranslation("contacts");
  if (!isRepeat) return null;
  return (
    <span className="flex items-center gap-2">
      <Badge variant="secondary">{t("profile.repeat")}</Badge>
      <span className="text-muted-foreground text-xs">
        {t("profile.booking_count", { count: bookingCount })}
      </span>
    </span>
  );
}
