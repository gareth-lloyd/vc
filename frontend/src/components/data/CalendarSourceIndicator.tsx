import { CalendarClock, ExternalLink } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/cn";

interface CalendarSourceIndicatorProps {
  /** True when the property has an active `PropertyCalendarFeed` (GAP-034). */
  hasActiveIcalFeed: boolean;
  /** The owner's online (non-iCal) calendar webpage, if any. */
  calendarUrl?: string | null;
  className?: string;
}

/**
 * Tells sales where a villa's on-screen availability comes from (GAP-034):
 * an "iCal" badge when VC auto-syncs the owner's feed, otherwise a quick link
 * to the owner's online calendar. The active feed always wins (it is the
 * latest-from-owner source), so the link is suppressed when a feed is present.
 * Renders nothing when there is neither.
 */
export function CalendarSourceIndicator({
  hasActiveIcalFeed,
  calendarUrl,
  className,
}: CalendarSourceIndicatorProps) {
  const { t } = useTranslation("common");

  if (hasActiveIcalFeed) {
    return (
      <Badge
        variant="outline"
        className={cn("border-info/40 bg-info/10 text-info gap-1 font-medium", className)}
        title={t("calendar_source.ical_tooltip")}
      >
        <CalendarClock className="size-3.5" aria-hidden />
        {t("calendar_source.ical_badge")}
      </Badge>
    );
  }

  if (calendarUrl) {
    return (
      <a
        href={calendarUrl}
        target="_blank"
        rel="noreferrer"
        className={cn(
          "text-primary inline-flex w-fit items-center gap-1 text-xs font-medium underline-offset-4 hover:underline",
          className,
        )}
      >
        <ExternalLink className="size-3.5" aria-hidden />
        {t("calendar_source.online_link")}
      </a>
    );
  }

  return null;
}
