import { useTranslation } from "react-i18next";
import { useOutletContext } from "react-router-dom";
import { FactList, FactRow } from "@/components/data/FactList";
import { Section } from "@/components/data/Section";
import type { CompanyOutletContext } from "../CompanyDetailLayout";

export function DetailsTab() {
  const { t } = useTranslation("companies");
  const { company } = useOutletContext<CompanyOutletContext>();

  return (
    <div className="space-y-8 p-6">
      <Section title={t("headings.overview")}>
        <FactList>
          <FactRow label={t("fields.name")} value={company.name || "—"} />
          <FactRow label={t("fields.org_type")} value={t(`org_type.${company.org_type}`)} />
          <FactRow label={t("fields.email")} value={company.email || "—"} />
          <FactRow label={t("fields.phone")} value={company.phone || "—"} />
          <FactRow label={t("fields.address_line_1")} value={company.address_line_1 || "—"} />
          <FactRow label={t("fields.address_line_2")} value={company.address_line_2 || "—"} />
          <FactRow label={t("fields.town")} value={company.town || "—"} />
          <FactRow label={t("fields.post_code")} value={company.post_code || "—"} />
          <FactRow
            label={t("fields.website")}
            value={
              company.website_url ? (
                <a
                  href={company.website_url}
                  target="_blank"
                  rel="noreferrer"
                  className="hover:underline"
                >
                  {company.website_url}
                </a>
              ) : (
                "—"
              )
            }
          />
          <FactRow
            label={t("fields.notes")}
            value={
              company.notes ? <span className="whitespace-pre-line">{company.notes}</span> : "—"
            }
          />
        </FactList>
      </Section>
    </div>
  );
}
