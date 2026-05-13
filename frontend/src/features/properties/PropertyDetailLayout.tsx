import { NavLink, Outlet, useParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { TwoColumn } from "@/components/layout/TwoColumn";
import { StatusBadge } from "@/components/data/StatusBadge";
import { ErrorState } from "@/components/feedback/ErrorState";
import { QuickActions, type QuickAction } from "@/components/feedback/QuickActions";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/cn";
import { useProperty } from "./hooks";

export const PROPERTY_TABS = [
  { slug: "details", label: "Details" },
  { slug: "pricing", label: "Pricing" },
  { slug: "availability", label: "Availability" },
  { slug: "people", label: "People" },
  { slug: "media", label: "Media" },
  { slug: "settings", label: "Settings" },
] as const;

const QUICK_ACTIONS: readonly QuickAction[] = [
  { label: "Open in availability" },
  { label: "Create booking" },
  { label: "Create quote" },
];

export function PropertyDetailLayout() {
  const { id } = useParams<{ id: string }>();
  const query = useProperty(id);

  if (query.isLoading) {
    return (
      <div className="space-y-4 p-6">
        <Skeleton className="h-8 w-1/3" />
        <Skeleton className="h-4 w-1/4" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (query.isError || !query.data) {
    return (
      <div className="p-6">
        <ErrorState
          title="Couldn't load this property"
          description="Try again or head back to the list."
          onRetry={() => query.refetch()}
        />
      </div>
    );
  }

  const property = query.data;

  return (
    <div>
      <PageHeader
        title={property.name}
        subtitle={
          property.display_name && property.display_name !== property.name
            ? property.display_name
            : undefined
        }
        breadcrumbs={[{ label: "Properties", to: "/properties" }, { label: property.name }]}
      />

      <div className="border-border border-b px-6">
        <nav className="flex gap-1" aria-label="Property sections">
          {PROPERTY_TABS.map((tab) => (
            <NavLink
              key={tab.slug}
              to={tab.slug}
              className={({ isActive }) =>
                cn(
                  "border-b-2 px-3 py-2 text-sm font-medium",
                  isActive
                    ? "border-foreground text-foreground"
                    : "text-muted-foreground hover:text-foreground border-transparent",
                )
              }
            >
              {tab.label}
            </NavLink>
          ))}
        </nav>
      </div>

      <TwoColumn
        rightRail={
          <div className="space-y-4">
            <div
              className="bg-muted aspect-[4/3] w-full rounded-md"
              aria-label="Property image placeholder"
            />
            <div>
              <h2 className="text-foreground text-lg font-semibold">{property.name}</h2>
              <p className="text-muted-foreground text-sm">{property.display_name || "—"}</p>
            </div>
            <StatusBadge status={property.status} />
            <QuickActions actions={QUICK_ACTIONS} />
          </div>
        }
      >
        <Outlet context={{ property }} />
      </TwoColumn>
    </div>
  );
}
