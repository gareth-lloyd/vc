import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useOutletContext } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { StatusBadge } from "@/components/data/StatusBadge";
import { FactList, FactRow } from "@/components/data/FactList";
import { formatDate } from "@/lib/format/date";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import type { EnquiryOutletContext } from "../EnquiryDetailLayout";
import { EnquiryFormDialog } from "../components/EnquiryFormDialog";
import { enquiryRequestTypeLabel, enquirySourceLabel, enquiryStatusLabel } from "../schemas";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="text-foreground text-base font-semibold">{title}</h2>
      {children}
    </section>
  );
}

export function DetailsTab() {
  const { t } = useTranslation("enquiries");
  const { enquiry } = useOutletContext<EnquiryOutletContext>();
  const hasRole = useHasReservationsRole();
  const [editOpen, setEditOpen] = useState(false);

  const fullName = `${enquiry.first_name ?? ""} ${enquiry.last_name ?? ""}`.trim() || "—";

  const partyText = (() => {
    const adults = enquiry.adults;
    const children = enquiry.children ?? 0;
    const adultsText = t("details_tab.values.adults", { count: adults });
    const childrenText = children ? t("details_tab.values.children", { count: children }) : "";
    return `${adultsText}${childrenText}`;
  })();

  const editButton = (
    <Button variant="outline" size="sm" onClick={() => setEditOpen(true)} disabled={!hasRole}>
      {t("details_tab.edit_button")}
    </Button>
  );

  return (
    <div className="space-y-8 p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-foreground text-lg font-semibold">{t("details_tab.heading")}</h2>
        {hasRole ? (
          editButton
        ) : (
          <Tooltip>
            <TooltipTrigger asChild>
              <span>{editButton}</span>
            </TooltipTrigger>
            <TooltipContent>{t("common:errors.reservations_role_required")}</TooltipContent>
          </Tooltip>
        )}
      </div>

      <Section title={t("details_tab.sections.status_and_dates")}>
        <FactList>
          <FactRow
            label={t("details_tab.fields.reference")}
            value={<span className="font-mono">{enquiry.reference}</span>}
          />
          <FactRow
            label={t("details_tab.fields.status")}
            value={<StatusBadge status={enquiryStatusLabel(enquiry.status)} />}
          />
          <FactRow
            label={t("details_tab.fields.from")}
            value={formatDate(enquiry.date_from ?? null)}
          />
          <FactRow label={t("details_tab.fields.to")} value={formatDate(enquiry.date_to ?? null)} />
          <FactRow
            label={t("details_tab.fields.flexible")}
            value={enquiry.is_flexible ? t("details_tab.values.yes") : t("details_tab.values.no")}
          />
          <FactRow
            label={t("details_tab.fields.created")}
            value={formatDate(enquiry.created_at ?? null)}
          />
        </FactList>
      </Section>

      <Section title={t("details_tab.sections.guest")}>
        <FactList>
          <FactRow label={t("details_tab.fields.name")} value={fullName} />
          <FactRow label={t("details_tab.fields.email")} value={enquiry.email || "—"} />
          <FactRow label={t("details_tab.fields.party")} value={partyText} />
          <FactRow
            label={t("details_tab.fields.min_bedrooms")}
            value={enquiry.min_bedrooms ?? "—"}
          />
        </FactList>
      </Section>

      <Section title={t("details_tab.sections.lead")}>
        <FactList>
          <FactRow
            label={t("details_tab.fields.source")}
            value={enquirySourceLabel(enquiry.site_source)}
          />
          <FactRow
            label={t("details_tab.fields.request_type")}
            value={enquiryRequestTypeLabel(enquiry.request_type)}
          />
          <FactRow
            label={t("details_tab.fields.property")}
            value={
              enquiry.property != null
                ? t("details_tab.values.id_ref", { id: enquiry.property })
                : "—"
            }
          />
          <FactRow
            label={t("details_tab.fields.region")}
            value={
              enquiry.region != null ? t("details_tab.values.id_ref", { id: enquiry.region }) : "—"
            }
          />
          <FactRow
            label={t("details_tab.fields.agent")}
            value={
              enquiry.agent != null ? t("details_tab.values.id_ref", { id: enquiry.agent }) : "—"
            }
          />
          <FactRow
            label={t("details_tab.fields.referral_code")}
            value={enquiry.referral_code || "—"}
          />
        </FactList>
      </Section>

      {enquiry.inbound_message ? (
        <Section title={t("details_tab.sections.inbound_message")}>
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
