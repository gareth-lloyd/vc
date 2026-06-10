import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import { format } from "date-fns";
import { PageHeader } from "@/components/layout/PageHeader";
import { Toolbar } from "@/components/data/Toolbar";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/cn";
import { PROPERTIES_PAGE_SIZE } from "@/features/properties/hooks";
import { useCollections, useMultiAvailability, useRegions, useTimelineProperties } from "./hooks";
import { hasAnyFilter, type TimelineFilters } from "./schemas";
import { bandStatusClasses, type BandDisplayStatus } from "./status";
import { useTimelineWindow } from "./useTimelineWindow";
import { TimelineGrid } from "./components/TimelineGrid";

const ALL_VALUE = "__all__";

const COUNTRY_VALUES = ["es", "fr", "it", "pt", "gr"] as const;
const COUNTRY_ISO = { es: "ES", fr: "FR", it: "IT", pt: "PT", gr: "GR" } as const;
const STATUS_VALUES = ["active", "draft", "archived"] as const;
const BEDROOM_VALUES = [2, 3, 4, 5, 6] as const;

// No default filters: a default would silently satisfy the force-filter gate.
function paramsToFilters(params: URLSearchParams): TimelineFilters {
  const page = Number(params.get("page") ?? "1");
  const minBedrooms = Number(params.get("min_bedrooms") ?? "");
  return {
    q: params.get("q") ?? undefined,
    country: params.get("country") ?? undefined,
    region: params.get("region") ?? undefined,
    collection: params.get("collection") ?? undefined,
    min_bedrooms: Number.isFinite(minBedrooms) && minBedrooms > 0 ? minBedrooms : undefined,
    status: params.get("status") ?? undefined,
    page: Number.isFinite(page) && page > 0 ? page : 1,
  };
}

const LEGEND: BandDisplayStatus[] = ["booked", "on_hold", "stop_sale"];

export function AvailabilityTimelinePage() {
  const { t } = useTranslation("availability");
  const [params, setParams] = useSearchParams();
  // Stringify-keyed memo: useSearchParams' URLSearchParams identity changes on every render.
  const filters = useMemo(() => paramsToFilters(params), [params.toString()]); // eslint-disable-line react-hooks/exhaustive-deps
  const [search, setSearch] = useState(filters.q ?? "");
  const filtered = hasAnyFilter(filters);

  const window = useTimelineWindow();
  const propertiesQuery = useTimelineProperties(filters);
  const properties = useMemo(() => propertiesQuery.data?.results ?? [], [propertiesQuery.data]);
  const propertyIds = useMemo(() => properties.map((p) => p.id), [properties]);
  const availabilityQuery = useMultiAvailability(propertyIds, window.from, window.to);
  const regions = useRegions();
  const collections = useCollections();

  useEffect(() => {
    setSearch(filters.q ?? "");
  }, [filters.q]);

  useEffect(() => {
    const current = filters.q ?? "";
    if (search === current) return;
    const handle = setTimeout(() => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (search) next.set("q", search);
          else next.delete("q");
          next.delete("page");
          return next;
        },
        { replace: true },
      );
    }, 250);
    return () => clearTimeout(handle);
  }, [search, filters.q, setParams]);

  const updateParam = (key: string, value: string | undefined) => {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (value && value !== ALL_VALUE) next.set(key, value);
        else next.delete(key);
        next.delete("page");
        return next;
      },
      { replace: true },
    );
  };

  const goToPage = (page: number) => {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (page <= 1) next.delete("page");
        else next.set("page", String(page));
        return next;
      },
      { replace: true },
    );
  };

  const count = propertiesQuery.data?.count ?? 0;
  const page = filters.page ?? 1;
  const pageCount = Math.max(1, Math.ceil(count / PROPERTIES_PAGE_SIZE));

  const filterSelect = (
    key: "country" | "region" | "collection" | "min_bedrooms" | "status",
    value: string | undefined,
    options: Array<{ value: string; label: string }>,
    aria: string,
  ) => (
    <Select value={value ?? ALL_VALUE} onValueChange={(v) => updateParam(key, v)}>
      <SelectTrigger className="w-[160px]" aria-label={aria}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );

  const body = () => {
    if (!filtered) {
      return <EmptyState title={t("gate.title")} description={t("gate.description")} />;
    }
    if (propertiesQuery.isLoading) {
      return <Skeleton className="h-64 w-full" />;
    }
    if (propertiesQuery.isError) {
      return (
        <ErrorState
          description={t("errors.properties_failed")}
          onRetry={() => propertiesQuery.refetch()}
          retrying={propertiesQuery.isFetching}
        />
      );
    }
    if (properties.length === 0) {
      return <EmptyState title={t("empty.title")} description={t("empty.description")} />;
    }
    if (availabilityQuery.isError) {
      return (
        <ErrorState
          description={t("errors.availability_failed")}
          onRetry={() => availabilityQuery.refetch()}
          retrying={availabilityQuery.isFetching}
        />
      );
    }
    return (
      <>
        {count > PROPERTIES_PAGE_SIZE ? (
          <div className="text-muted-foreground flex items-center justify-between gap-4 text-sm">
            <span>{t("refine.notice", { pageSize: PROPERTIES_PAGE_SIZE, count })}</span>
            <span className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => goToPage(page - 1)}
              >
                {t("refine.prev")}
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= pageCount}
                onClick={() => goToPage(page + 1)}
              >
                {t("refine.next")}
              </Button>
            </span>
          </div>
        ) : null}
        <TimelineGrid
          days={window.days}
          windowStart={window.start}
          properties={properties}
          holds={availabilityQuery.data?.records ?? []}
          bookings={availabilityQuery.data?.bookings ?? []}
        />
      </>
    );
  };

  return (
    <div>
      <PageHeader
        title={t("page.title")}
        breadcrumbs={[{ label: t("page.breadcrumb_operations") }, { label: t("page.title") }]}
      />
      <div className="space-y-4 p-6">
        <Toolbar
          searchValue={search}
          onSearchChange={setSearch}
          searchPlaceholder={t("filters.search_placeholder")}
          searchAriaLabel={t("filters.search_aria")}
          filters={
            <>
              {filterSelect(
                "country",
                filters.country,
                [
                  { value: ALL_VALUE, label: t("common:filters.any_country") },
                  ...COUNTRY_VALUES.map((v) => ({
                    value: v,
                    label: t(`common:countries.${COUNTRY_ISO[v]}`),
                  })),
                ],
                t("filters.country_aria"),
              )}
              {filterSelect(
                "region",
                filters.region,
                [
                  { value: ALL_VALUE, label: t("filters.any_region") },
                  ...(regions.data?.results ?? []).map((r) => ({ value: r.slug, label: r.name })),
                ],
                t("filters.region_aria"),
              )}
              {filterSelect(
                "collection",
                filters.collection,
                [
                  { value: ALL_VALUE, label: t("filters.any_collection") },
                  ...(collections.data?.results ?? []).map((c) => ({
                    value: c.slug,
                    label: c.name,
                  })),
                ],
                t("filters.collection_aria"),
              )}
              {filterSelect(
                "min_bedrooms",
                filters.min_bedrooms ? String(filters.min_bedrooms) : undefined,
                [
                  { value: ALL_VALUE, label: t("filters.any_bedrooms") },
                  ...BEDROOM_VALUES.map((n) => ({
                    value: String(n),
                    label: t("filters.min_bedrooms", { count: n }),
                  })),
                ],
                t("filters.bedrooms_aria"),
              )}
              {filterSelect(
                "status",
                filters.status,
                [
                  { value: ALL_VALUE, label: t("properties:status.any") },
                  ...STATUS_VALUES.map((v) => ({ value: v, label: t(`properties:status.${v}`) })),
                ],
                t("filters.status_aria"),
              )}
            </>
          }
          rightSlot={
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={window.goPrev}>
                {t("window.prev")}
              </Button>
              <Button variant="ghost" size="sm" onClick={window.goToday}>
                {t("window.today")}
              </Button>
              <Button variant="outline" size="sm" onClick={window.goNext}>
                {t("window.next")}
              </Button>
              <span className="text-muted-foreground min-w-[150px] text-center text-sm">
                {format(window.days[0], "d MMM")} –{" "}
                {format(window.days[window.days.length - 1], "d MMM yyyy")}
              </span>
            </div>
          }
        />

        <div className="flex flex-wrap gap-4 text-xs">
          <span className="flex items-center gap-1">
            <span className="border-border inline-block h-3 w-3 rounded border" />
            {t("legend.available")}
          </span>
          {LEGEND.map((status) => (
            <span key={status} className="flex items-center gap-1">
              <span className={cn("inline-block h-3 w-3 rounded", bandStatusClasses(status))} />
              {t(`legend.${status}`)}
            </span>
          ))}
        </div>

        {body()}
      </div>
    </div>
  );
}
