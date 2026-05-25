import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { TwoColumn } from "@/components/layout/TwoColumn";
import { StatusBadge } from "@/components/data/StatusBadge";
import { ErrorState } from "@/components/feedback/ErrorState";
import { QuickActions, type QuickAction } from "@/components/feedback/QuickActions";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/cn";
import { ApiError } from "@/lib/api/errors";
import { useProperty } from "./hooks";

export const PROPERTY_TABS = [
  { slug: "details", labelKey: "tabs.details" },
  { slug: "rooms", labelKey: "tabs.rooms" },
  { slug: "nearby", labelKey: "tabs.nearby" },
  { slug: "pricing", labelKey: "tabs.pricing" },
  { slug: "availability", labelKey: "tabs.availability" },
  { slug: "people", labelKey: "tabs.people" },
  { slug: "media", labelKey: "tabs.media" },
  { slug: "features", labelKey: "tabs.features" },
  { slug: "settings", labelKey: "tabs.settings" },
] as const;
export type PropertyTabSlug = (typeof PROPERTY_TABS)[number]["slug"];
export const PROPERTY_TAB_SLUGS: readonly PropertyTabSlug[] = PROPERTY_TABS.map((t) => t.slug);

export function PropertyDetailLayout() {
  const { t } = useTranslation("properties");
  const { id } = useParams<{ id: string }>();
  const query = useProperty(id);

  const quickActions = useMemo<readonly QuickAction[]>(
    () => [
      { label: t("detail.quick_actions.open_in_availability") },
      { label: t("detail.quick_actions.create_booking") },
      { label: t("detail.quick_actions.create_quote") },
    ],
    [t],
  );

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
    const is404 = query.error instanceof ApiError && query.error.status === 404;
    return (
      <div className="p-6">
        <ErrorState
          title={is404 ? t("detail.not_found_title") : t("detail.load_failed_title")}
          description={is404 ? t("detail.not_found_body") : t("detail.load_failed_body")}
          onRetry={is404 ? undefined : () => query.refetch()}
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
        breadcrumbs={[
          { label: t("detail.breadcrumb_list"), to: "/properties" },
          { label: property.name },
        ]}
      />

      <div className="border-border border-b px-6">
        <nav className="flex gap-1" aria-label={t("detail.sections_aria")}>
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
              {t(tab.labelKey)}
            </NavLink>
          ))}
        </nav>
      </div>

      <TwoColumn
        rightRail={
          <div className="space-y-4">
            <div
              className="bg-muted aspect-[4/3] w-full rounded-md"
              aria-label={t("detail.image_placeholder_aria")}
            />
            <div>
              <h2 className="text-foreground font-serif text-lg font-semibold">{property.name}</h2>
              <p className="text-muted-foreground text-sm">
                {property.display_name || t("detail.subtitle_dash")}
              </p>
            </div>
            <StatusBadge status={property.status} />
            <QuickActions actions={quickActions} />
          </div>
        }
      >
        <Outlet context={{ property }} />
      </TwoColumn>
    </div>
  );
}
