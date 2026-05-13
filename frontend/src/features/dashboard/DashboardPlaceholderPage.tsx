import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/feedback/EmptyState";

export function DashboardPlaceholderPage() {
  return (
    <div>
      <PageHeader
        title="Dashboard"
        subtitle="An operator overview will live here in the next phase."
      />
      <div className="p-6">
        <EmptyState
          title="Dashboard coming soon"
          description="KPIs, arrivals/departures, recent enquiries, and overdue balances will land in Phase 2."
        />
      </div>
    </div>
  );
}
