import { useTranslation } from "react-i18next";
import { PageHeader } from "@/components/layout/PageHeader";
import { formatDate } from "@/lib/format/date";
import { KpiCard } from "./components/KpiCard";
import { ArrivalsList } from "./components/ArrivalsList";
import { RecentEnquiriesList } from "./components/RecentEnquiriesList";
import {
  todayIso,
  useArrivalsToday,
  useAwaitingBalanceCount,
  useDeparturesTodayCount,
  useNewEnquiriesCount,
} from "./hooks";

export function DashboardPage() {
  const { t } = useTranslation("dashboard");
  const today = todayIso();

  const arrivals = useArrivalsToday();
  const departures = useDeparturesTodayCount();
  const newEnquiries = useNewEnquiriesCount();
  const awaitingBalance = useAwaitingBalanceCount();

  const errorLabel = t("errors.card");

  return (
    <div>
      <PageHeader title={t("title")} subtitle={t("subtitle_today", { date: formatDate(today) })} />
      <div className="space-y-6 p-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <KpiCard
            label={t("kpis.check_ins_today")}
            value={arrivals.data?.count}
            to={`/bookings?check_in_after=${today}&check_in_before=${today}`}
            loading={arrivals.isLoading}
            error={arrivals.isError}
            errorLabel={errorLabel}
          />
          <KpiCard
            label={t("kpis.check_outs_today")}
            value={departures.data}
            to={`/bookings?check_out_after=${today}&check_out_before=${today}`}
            loading={departures.isLoading}
            error={departures.isError}
            errorLabel={errorLabel}
          />
          <KpiCard
            label={t("kpis.new_enquiries")}
            sublabel={t("kpis.new_enquiries_sub")}
            value={newEnquiries.data}
            to="/enquiries?status=new"
            loading={newEnquiries.isLoading}
            error={newEnquiries.isError}
            errorLabel={errorLabel}
          />
          <KpiCard
            label={t("kpis.awaiting_balance")}
            sublabel={t("kpis.awaiting_balance_sub")}
            value={awaitingBalance.data}
            to="/bookings?status=awaiting_balance"
            loading={awaitingBalance.isLoading}
            error={awaitingBalance.isError}
            errorLabel={errorLabel}
          />
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <ArrivalsList />
          <RecentEnquiriesList />
        </div>
      </div>
    </div>
  );
}
