import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { StatusBadge } from "@/components/data/StatusBadge";
import { FactList, FactRow } from "@/components/data/FactList";
import { formatDate } from "@/lib/format/date";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import type { EnquiryOutletContext } from "../EnquiryDetailLayout";
import { EnquiryFormDialog } from "../components/EnquiryFormDialog";
import { ENQUIRY_SOURCE_LABELS, ENQUIRY_STATUS_LABELS } from "../schemas";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="text-foreground text-base font-semibold">{title}</h2>
      {children}
    </section>
  );
}

export function DetailsTab() {
  const { enquiry } = useOutletContext<EnquiryOutletContext>();
  const hasRole = useHasReservationsRole();
  const [editOpen, setEditOpen] = useState(false);

  const fullName = `${enquiry.first_name ?? ""} ${enquiry.last_name ?? ""}`.trim() || "—";
  const editButton = (
    <Button variant="outline" size="sm" onClick={() => setEditOpen(true)} disabled={!hasRole}>
      Edit details
    </Button>
  );

  return (
    <div className="space-y-8 p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-foreground text-lg font-semibold">Enquiry details</h2>
        {hasRole ? (
          editButton
        ) : (
          <Tooltip>
            <TooltipTrigger asChild>
              <span>{editButton}</span>
            </TooltipTrigger>
            <TooltipContent>Reservations role required.</TooltipContent>
          </Tooltip>
        )}
      </div>

      <Section title="Status & key dates">
        <FactList>
          <FactRow
            label="Reference"
            value={<span className="font-mono">{enquiry.reference}</span>}
          />
          <FactRow
            label="Status"
            value={<StatusBadge status={ENQUIRY_STATUS_LABELS[enquiry.status]} />}
          />
          <FactRow label="From" value={formatDate(enquiry.date_from ?? null)} />
          <FactRow label="To" value={formatDate(enquiry.date_to ?? null)} />
          <FactRow label="Flexible" value={enquiry.is_flexible ? "Yes" : "No"} />
          <FactRow label="Created" value={formatDate(enquiry.created_at ?? null)} />
        </FactList>
      </Section>

      <Section title="Guest">
        <FactList>
          <FactRow label="Name" value={fullName} />
          <FactRow label="Email" value={enquiry.email || "—"} />
          <FactRow
            label="Party"
            value={`${enquiry.adults} adult${enquiry.adults === 1 ? "" : "s"}${
              enquiry.children
                ? `, ${enquiry.children} child${enquiry.children === 1 ? "" : "ren"}`
                : ""
            }`}
          />
          <FactRow label="Min bedrooms" value={enquiry.min_bedrooms ?? "—"} />
        </FactList>
      </Section>

      <Section title="Lead">
        <FactList>
          <FactRow label="Source" value={ENQUIRY_SOURCE_LABELS[enquiry.site_source]} />
          <FactRow
            label="Request type"
            value={<span className="capitalize">{enquiry.request_type}</span>}
          />
          <FactRow
            label="Property"
            value={enquiry.property != null ? `#${enquiry.property}` : "—"}
          />
          <FactRow label="Region" value={enquiry.region != null ? `#${enquiry.region}` : "—"} />
          <FactRow label="Agent" value={enquiry.agent != null ? `#${enquiry.agent}` : "—"} />
          <FactRow label="Referral code" value={enquiry.referral_code || "—"} />
        </FactList>
      </Section>

      {enquiry.inbound_message ? (
        <Section title="Inbound message">
          <p className="text-foreground bg-muted/40 rounded-md border p-3 text-sm whitespace-pre-line">
            {enquiry.inbound_message}
          </p>
        </Section>
      ) : null}

      {editOpen && (
        <EnquiryFormDialog
          mode="edit"
          enquiry={enquiry}
          open={editOpen}
          onOpenChange={setEditOpen}
        />
      )}
    </div>
  );
}
