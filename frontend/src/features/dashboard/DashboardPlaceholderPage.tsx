import { useTranslation } from "react-i18next";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/feedback/EmptyState";

export function DashboardPlaceholderPage() {
  const { t } = useTranslation("dashboard");
  return (
    <div>
      <PageHeader title={t("placeholder.title")} subtitle={t("placeholder.subtitle")} />
      <div className="p-6">
        <EmptyState
          title={t("placeholder.empty_title")}
          description={t("placeholder.empty_description")}
        />
      </div>
    </div>
  );
}
