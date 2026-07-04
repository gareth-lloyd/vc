import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";
import type { SortingState } from "@tanstack/react-table";
import { Plus } from "lucide-react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Toolbar } from "@/components/data/Toolbar";
import { DataTable } from "@/components/data/DataTable";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { orderingToSorting, sortingToOrdering } from "@/lib/drf/sorting";
import { propertyDetailsPath } from "@/lib/routes";
import { useCountries } from "@/features/admin/countries/hooks";
import { useRegions } from "@/features/availability/hooks";
import { TAXONOMY_PAGE_SIZE } from "./api";
import { regionOptionsForCountry } from "./regionOptions";
import { CreatePropertyDialog } from "./components/CreatePropertyDialog";
import { propertyColumns } from "./columns";
import { PROPERTIES_PAGE_SIZE, useProperties } from "./hooks";
import type { PropertyFilters, PropertyListItem } from "./schemas";

const ALL_VALUE = "__all__";

const STATUS_VALUES = ["active", "draft", "archived"] as const;

function paramsToFilters(params: URLSearchParams): PropertyFilters {
  const page = Number(params.get("page") ?? "1");
  return {
    q: params.get("q") ?? undefined,
    country: params.get("country") ?? undefined,
    region: params.get("region") ?? undefined,
    status: params.get("status") ?? undefined,
    ordering: params.get("ordering") ?? undefined,
    page: Number.isFinite(page) && page > 0 ? page : 1,
  };
}

export function PropertiesListPage() {
  const { t } = useTranslation("properties");
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  // Stringify-keyed memo: useSearchParams' URLSearchParams identity changes on every render.
  const filters = useMemo(() => paramsToFilters(params), [params.toString()]); // eslint-disable-line react-hooks/exhaustive-deps
  const [search, setSearch] = useState(filters.q ?? "");
  const [createOpen, setCreateOpen] = useState(false);
  const canCreate = useHasReservationsRole();
  const regionsQuery = useRegions();
  // In-use countries only — the filter should never offer a country that
  // cannot match a property. Labels come from the API name field.
  const countriesQuery = useCountries({
    hasProperties: true,
    ordering: "name",
    pageSize: TAXONOMY_PAGE_SIZE,
  });

  const countryOptions = [
    { value: ALL_VALUE, label: t("common:filters.any_country") },
    // Uppercase to match the Select-value mapping below — Country.iso2 has no
    // server-side case normalisation.
    ...(countriesQuery.data?.results ?? []).map((c) => ({
      value: c.iso2.toUpperCase(),
      label: c.name,
    })),
  ];

  // Region value is the globally-unique id (slug/name are unique only per
  // country, so both repeat across countries); options scope to the chosen
  // country so impossible combos are never offered. filter_region accepts
  // id or slug.
  const regionOptions = [
    { value: ALL_VALUE, label: t("common:filters.any_region") },
    ...regionOptionsForCountry(regionsQuery.data?.results ?? [], filters.country, filters.region),
  ];

  const statusOptions = [
    { value: ALL_VALUE, label: t("status.any") },
    ...STATUS_VALUES.map((v) => ({ value: v, label: t(`status.${v}`) })),
  ];

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

  // Multi-key so dependent filters clear together in one history entry
  // (changing country must also clear region).
  const updateParams = (entries: Record<string, string | undefined>) => {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        for (const [key, value] of Object.entries(entries)) {
          if (value && value !== ALL_VALUE) next.set(key, value);
          else next.delete(key);
        }
        next.delete("page");
        return next;
      },
      { replace: true },
    );
  };
  const updateParam = (key: string, value: string | undefined) => updateParams({ [key]: value });

  const goToPage = (zeroBased: number) => {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (zeroBased <= 0) next.delete("page");
        else next.set("page", String(zeroBased + 1));
        return next;
      },
      { replace: true },
    );
  };

  const onSortingChange = (sorting: SortingState) => {
    updateParam("ordering", sortingToOrdering(sorting));
  };

  const query = useProperties(filters);
  const pageCount = query.data
    ? Math.max(1, Math.ceil(query.data.count / PROPERTIES_PAGE_SIZE))
    : 1;
  const sorting = useMemo(() => orderingToSorting(filters.ordering), [filters.ordering]);

  const handleRowClick = (row: PropertyListItem) => {
    const slug = row.slug?.trim();
    const isValidSlug = slug && !slug.includes("/");
    navigate(propertyDetailsPath(isValidSlug ? slug : row.id));
  };

  const newVillaButton = (
    <Button size="sm" disabled={!canCreate} onClick={() => setCreateOpen(true)}>
      <Plus className="size-4" />
      {t("create.button")}
    </Button>
  );

  return (
    <div>
      <PageHeader
        title={t("list.title")}
        breadcrumbs={[{ label: t("list.breadcrumb_library") }, { label: t("list.title") }]}
        actions={
          canCreate ? (
            newVillaButton
          ) : (
            // Convention: write affordances disable (with a reason), never disappear.
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="block">{newVillaButton}</span>
              </TooltipTrigger>
              <TooltipContent>{t("create.disabled_no_role")}</TooltipContent>
            </Tooltip>
          )
        }
      />
      <div className="space-y-4 p-6">
        <Toolbar
          searchValue={search}
          onSearchChange={setSearch}
          searchPlaceholder={t("list.search_placeholder")}
          filters={
            <>
              <Select
                // Option values are uppercase iso2 (as the API returns); old
                // lowercase bookmarks must still display their selection.
                value={filters.country?.toUpperCase() ?? ALL_VALUE}
                // A region from another country can no longer match — clear
                // it in the same history entry.
                onValueChange={(v) => updateParams({ country: v, region: undefined })}
              >
                <SelectTrigger className="w-[160px]" aria-label={t("list.filter_country_aria")}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {countryOptions.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select
                value={filters.region ?? ALL_VALUE}
                onValueChange={(v) => updateParam("region", v)}
              >
                <SelectTrigger className="w-[160px]" aria-label={t("list.filter_region_aria")}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {regionOptions.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select
                value={filters.status ?? ALL_VALUE}
                onValueChange={(v) => updateParam("status", v)}
              >
                <SelectTrigger className="w-[160px]" aria-label={t("list.filter_status_aria")}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {statusOptions.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </>
          }
        />

        {query.isError ? (
          <ErrorState
            description={t("list.load_failed")}
            onRetry={() => query.refetch()}
            retrying={query.isFetching}
          />
        ) : (
          <DataTable
            columns={propertyColumns}
            data={query.data?.results}
            isLoading={query.isLoading}
            pageIndex={(filters.page ?? 1) - 1}
            pageCount={pageCount}
            pageSize={PROPERTIES_PAGE_SIZE}
            sorting={sorting}
            onSortingChange={onSortingChange}
            onPageChange={goToPage}
            onRowClick={handleRowClick}
            rowKey={(row) => row.id}
            emptyContent={
              <EmptyState title={t("list.empty_title")} description={t("list.empty_hint")} />
            }
          />
        )}
      </div>
      {createOpen ? <CreatePropertyDialog open={createOpen} onOpenChange={setCreateOpen} /> : null}
    </div>
  );
}
