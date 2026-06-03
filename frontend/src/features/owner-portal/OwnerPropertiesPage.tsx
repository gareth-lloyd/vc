import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Building2 } from "lucide-react";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBadge } from "@/components/data/StatusBadge";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";
import { useOwnerProperties } from "./hooks";
import type { OwnerProperty } from "./schemas";

function PropertyCard({ property, onClick }: { property: OwnerProperty; onClick: () => void }) {
  const { t } = useTranslation("owner");
  const title = property.display_name || property.name;
  return (
    <button
      type="button"
      onClick={onClick}
      className="bg-card shadow-card focus-visible:ring-ring group block overflow-hidden rounded-lg border text-left transition-colors focus-visible:ring-2 focus-visible:outline-none"
    >
      <div className="bg-muted relative aspect-[3/2] w-full overflow-hidden">
        {property.hero_image_url ? (
          <img
            src={property.hero_image_url}
            alt={title}
            className="h-full w-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="text-muted-foreground flex h-full w-full items-center justify-center">
            <Building2 className="size-8" aria-hidden />
          </div>
        )}
      </div>
      <div className="space-y-2 p-4">
        <div className="flex items-start justify-between gap-2">
          <h3 className="text-foreground font-serif text-lg leading-tight font-semibold">
            {title}
          </h3>
          <StatusBadge status={property.status} />
        </div>
        <div className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-sm">
          {property.guests != null ? (
            <span>{t("properties.guests", { count: property.guests })}</span>
          ) : null}
          {property.bedrooms != null ? (
            <span>{t("properties.bedrooms", { count: property.bedrooms })}</span>
          ) : null}
        </div>
      </div>
    </button>
  );
}

export function OwnerPropertiesPage() {
  const { t } = useTranslation("owner");
  const navigate = useNavigate();
  const query = useOwnerProperties();
  const rows = query.data?.results ?? [];

  return (
    <div>
      <PageHeader title={t("properties.title")} subtitle={t("properties.subtitle")} />
      <div className="px-6 pb-12">
        {query.isError ? (
          <ErrorState description={t("properties.load_failed")} onRetry={() => query.refetch()} />
        ) : query.isLoading ? (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-64 w-full rounded-lg" />
            ))}
          </div>
        ) : rows.length === 0 ? (
          <EmptyState
            title={t("properties.empty_title")}
            description={t("properties.empty_hint")}
          />
        ) : (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {rows.map((property) => (
              <PropertyCard
                key={property.id}
                property={property}
                onClick={() => navigate(`/owner/properties/${property.id}/calendar`)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
