import { Badge } from "@/components/ui/badge";
import { formatDate } from "@/lib/format/date";
import { ENQUIRY_SOURCE_LABELS, type EnquiryListItem } from "../schemas";

interface EnquiryCardProps {
  enquiry: EnquiryListItem;
  onClick?: () => void;
}

function guestName(enq: EnquiryListItem): string {
  const name = `${enq.first_name ?? ""} ${enq.last_name ?? ""}`.trim();
  return name || enq.email || enq.reference;
}

function dateRange(enq: EnquiryListItem): string {
  if (!enq.date_from && !enq.date_to) return "Flexible dates";
  return `${formatDate(enq.date_from ?? null)} – ${formatDate(enq.date_to ?? null)}`;
}

function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (!Number.isFinite(then)) return "";
  const diffMs = Date.now() - then;
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return formatDate(iso);
}

export function EnquiryCard({ enquiry, onClick }: EnquiryCardProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="border-border bg-card hover:bg-accent/40 w-full space-y-2 rounded-md border p-3 text-left text-sm shadow-sm transition-colors"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="text-foreground font-medium">{guestName(enquiry)}</div>
        <span className="text-muted-foreground font-mono text-xs">{enquiry.reference}</span>
      </div>
      <div className="text-muted-foreground text-xs">
        {enquiry.property != null ? `Property #${enquiry.property}` : "No property"}
      </div>
      <div className="text-muted-foreground text-xs">{dateRange(enquiry)}</div>
      <div className="flex items-center justify-between gap-2">
        <Badge variant="outline" className="text-xs">
          {ENQUIRY_SOURCE_LABELS[enquiry.site_source]}
        </Badge>
        <span className="text-muted-foreground text-xs">{timeAgo(enquiry.created_at)}</span>
      </div>
    </button>
  );
}
