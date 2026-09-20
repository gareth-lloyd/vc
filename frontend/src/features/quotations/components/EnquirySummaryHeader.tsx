import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/data/StatusBadge";
import { formatDate } from "@/lib/format/date";
import { RepeatBadge } from "@/features/contacts/components/RepeatBadge";
import { TagChips } from "@/features/contacts/components/TagChips";
import { useContact } from "@/features/contacts/hooks";
import { EnquiryFormDialog } from "@/features/enquiries/components/EnquiryFormDialog";
import {
  enquiryRequestTypeLabel,
  enquirySourceLabel,
  guestName,
  type EnquiryDetail,
} from "@/features/enquiries/schemas";

interface Props {
  enquiry: EnquiryDetail;
}

/**
 * Compact recap of the enquiry the operator is quoting against, pinned to the
 * top of the builder: who's asking, the requested stay (with its ± flex), the
 * party, and the capture context. Edit opens the standard enquiry dialog; the
 * host's enquiry-detail cache invalidation refreshes the header after save.
 *
 * The linked client's tags and Repeat badge sit next to the name (GAP-116):
 * the builder hides the rail that normally shows them. Read-only — the contact
 * read shares the rail's cache entry, and renders nothing until it resolves.
 */
export function EnquirySummaryHeader({ enquiry }: Props) {
  const { t } = useTranslation("quotations");
  const [editOpen, setEditOpen] = useState(false);
  // GAP-118: the migration's unknown-client sentinel is a placeholder, not a
  // customer — drop it here so the header agrees with the rail's
  // `CustomerProfilePanel`, which renders it as "no customer linked". Every
  // read below already falls back for an absent contact.
  const { data } = useContact(enquiry.person ?? undefined);
  const contact = data?.is_unknown_client === true ? undefined : data;

  const facts: string[] = [];
  if (enquiry.date_from && enquiry.date_to) {
    const range = `${formatDate(enquiry.date_from)} → ${formatDate(enquiry.date_to)}`;
    facts.push(
      enquiry.flexibility_days > 0
        ? `${range} ${t("builder.summary.flex_days", { count: enquiry.flexibility_days })}`
        : range,
    );
  }
  facts.push(
    t("builder.summary.party", { adults: enquiry.adults, children: enquiry.children ?? 0 }),
  );
  if (enquiry.min_bedrooms != null && enquiry.min_bedrooms > 0) {
    facts.push(t("builder.summary.min_bedrooms", { count: enquiry.min_bedrooms }));
  }
  facts.push(enquiryRequestTypeLabel(enquiry.request_type));
  facts.push(enquirySourceLabel(enquiry.site_source));

  return (
    <header className="border-border bg-muted/40 flex items-start justify-between gap-3 rounded-md border p-3">
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-foreground truncate text-sm font-semibold">{guestName(enquiry)}</h3>
          <span className="text-muted-foreground text-xs">{enquiry.reference}</span>
          {enquiry.is_flexible ? (
            <StatusBadge status="flexible" kind="pending" label={t("builder.summary.flexible")} />
          ) : null}
          <RepeatBadge
            bookingCount={contact?.booking_count ?? 0}
            pastStayCount={contact?.past_stay_count ?? 0}
            isRepeat={contact?.is_repeat_customer ?? false}
          />
          <TagChips tags={contact?.tags ?? []} />
        </div>
        <p className="text-muted-foreground text-xs">{facts.join(" · ")}</p>
      </div>
      <Button type="button" variant="outline" size="sm" onClick={() => setEditOpen(true)}>
        <Pencil className="size-3.5" aria-hidden />
        {t("builder.summary.edit")}
      </Button>

      {editOpen ? (
        <EnquiryFormDialog mode="edit" enquiry={enquiry} open onOpenChange={setEditOpen} />
      ) : null}
    </header>
  );
}
