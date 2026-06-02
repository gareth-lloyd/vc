import { useTranslation } from "react-i18next";
import { ActivityList } from "@/components/data/ActivityList";
import { useOutletContext } from "react-router-dom";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { formatDate } from "@/lib/format/date";
import { useBookingActivity } from "../hooks";
import type { BookingOutletContext } from "../BookingDetailLayout";

function formatTransition(from: string | null, to: string) {
  if (!from || from === to) return to;
  return `${from} → ${to}`;
}

export function TimelineTab() {
  const { t } = useTranslation("bookings");
  const { booking } = useOutletContext<BookingOutletContext>();
  const activity = useBookingActivity(booking.id);

  if (activity.isLoading) {
    return (
      <div className="p-6">
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (activity.isError) {
    return (
      <div className="p-6">
        <ErrorState
          title={t("timeline.load_failed_title")}
          description={t("timeline.load_failed_body")}
          onRetry={() => activity.refetch()}
        />
      </div>
    );
  }

  const events = activity.data ?? [];
  if (events.length === 0) {
    return (
      <div className="p-6">
        <EmptyState title={t("timeline.empty_title")} description={t("timeline.empty_body")} />
      </div>
    );
  }

  return (
    <div className="p-6">
      <ActivityList as="ol">
        {events.map((event) => (
          <li key={event.id} className="px-4 py-3 text-sm">
            <div className="flex items-baseline justify-between gap-4">
              <span className="text-foreground font-medium">
                {formatTransition(event.from_status, event.to_status)}
              </span>
              <span className="text-muted-foreground text-xs">
                {formatDate(event.created_at)} · {event.source}
              </span>
            </div>
            {event.reason ? (
              <p className="text-muted-foreground mt-1 text-xs">{event.reason}</p>
            ) : null}
          </li>
        ))}
      </ActivityList>
    </div>
  );
}
