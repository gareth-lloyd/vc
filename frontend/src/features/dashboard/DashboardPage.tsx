import { useTranslation } from "react-i18next";
import { PageHeader } from "@/components/layout/PageHeader";
import { formatDate, todayIso } from "@/lib/format/date";
import { HeroArrivals } from "./components/HeroArrivals";
import { StatRail } from "./components/StatRail";
import { RecentEnquiriesList } from "./components/RecentEnquiriesList";

export function DashboardPage() {
  const { t } = useTranslation("dashboard");
  const today = todayIso();

  return (
    <div>
      <PageHeader title={t("title")} subtitle={t("subtitle_today", { date: formatDate(today) })} />
      <div className="space-y-8 px-6 pb-12">
        {/* Editorial spread: hero arrivals + vertical stat rail. */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <HeroArrivals />
          </div>
          <StatRail />
        </div>

        {/* Bottom strip: recent enquiries. Full-bleed. */}
        <RecentEnquiriesList />
      </div>
    </div>
  );
}
