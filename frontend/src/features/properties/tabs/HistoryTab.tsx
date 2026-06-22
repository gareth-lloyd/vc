import { useOutletContext } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { AuditHistory } from "@/features/audit/AuditHistory";
import type { PropertyDetail } from "../schemas";

interface PropertyHistoryContext {
  property: PropertyDetail;
}

export function HistoryTab() {
  const { t } = useTranslation("audit");
  const { property } = useOutletContext<PropertyHistoryContext>();
  return (
    <div className="space-y-8 p-6">
      <section className="space-y-3">
        <h3 className="text-foreground text-sm font-semibold">{t("sections.record")}</h3>
        <AuditHistory entityType="properties.property" entityId={property.id} />
      </section>
      <section className="space-y-3">
        <h3 className="text-foreground text-sm font-semibold">{t("sections.finance")}</h3>
        {/* PropertyFinance is a OneToOneField(primary_key=True) on property, so its
            audit object_id == the property id — no separate finance pk needed. */}
        <AuditHistory entityType="properties.propertyfinance" entityId={property.id} />
      </section>
    </div>
  );
}
