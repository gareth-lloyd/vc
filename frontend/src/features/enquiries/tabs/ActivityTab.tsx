import { useOutletContext } from "react-router-dom";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { formatDate } from "@/lib/format/date";
import { useEnquiryActivity } from "../hooks";
import type { EnquiryOutletContext } from "../EnquiryDetailLayout";

function formatTransition(from: string | null, to: string, kind: string) {
  if (!from || from === to) return kind.replace(/_/g, " ");
  return `${from} → ${to}`;
}

export function ActivityTab() {
  const { enquiry } = useOutletContext<EnquiryOutletContext>();
  const activity = useEnquiryActivity(enquiry.id);

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
          title="Couldn't load activity"
          description="Try again."
          onRetry={() => activity.refetch()}
        />
      </div>
    );
  }

  const events = activity.data ?? [];
  if (events.length === 0) {
    return (
      <div className="p-6">
        <EmptyState title="No activity yet" description="Lifecycle events will appear here." />
      </div>
    );
  }

  return (
    <div className="p-6">
      <ol className="border-border bg-card divide-border divide-y rounded-lg border">
        {events.map((event) => (
          <li key={event.id} className="px-4 py-3 text-sm">
            <div className="flex items-baseline justify-between gap-4">
              <span className="text-foreground font-medium">
                {formatTransition(event.from_status, event.to_status, event.kind)}
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
      </ol>
    </div>
  );
}
