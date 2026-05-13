import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import type { SortingState } from "@tanstack/react-table";
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
import { orderingToSorting, sortingToOrdering } from "@/lib/drf/sorting";
import { propertyColumns } from "./columns";
import { PROPERTIES_PAGE_SIZE, useProperties } from "./hooks";
import type { PropertyFilters, PropertyListItem } from "./schemas";

const ALL_VALUE = "__all__";

const COUNTRY_OPTIONS = [
  { value: ALL_VALUE, label: "All countries" },
  { value: "es", label: "Spain" },
  { value: "fr", label: "France" },
  { value: "it", label: "Italy" },
  { value: "pt", label: "Portugal" },
  { value: "gr", label: "Greece" },
];

const STATUS_OPTIONS = [
  { value: ALL_VALUE, label: "Any status" },
  { value: "active", label: "Active" },
  { value: "draft", label: "Draft" },
  { value: "archived", label: "Archived" },
];

function paramsToFilters(params: URLSearchParams): PropertyFilters {
  const page = Number(params.get("page") ?? "1");
  return {
    q: params.get("q") ?? undefined,
    country: params.get("country") ?? undefined,
    status: params.get("status") ?? undefined,
    ordering: params.get("ordering") ?? undefined,
    page: Number.isFinite(page) && page > 0 ? page : 1,
  };
}

export function PropertiesListPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  // Stringify-keyed memo: useSearchParams' URLSearchParams identity changes on every render.
  const filters = useMemo(() => paramsToFilters(params), [params.toString()]); // eslint-disable-line react-hooks/exhaustive-deps
  const [search, setSearch] = useState(filters.q ?? "");

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
    navigate(`/properties/${isValidSlug ? slug : row.id}/details`);
  };

  return (
    <div>
      <PageHeader
        title="Properties"
        breadcrumbs={[{ label: "Library" }, { label: "Properties" }]}
      />
      <div className="space-y-4 p-6">
        <Toolbar
          searchValue={search}
          onSearchChange={setSearch}
          searchPlaceholder="Search by name or slug…"
          filters={
            <>
              <Select
                value={filters.country ?? ALL_VALUE}
                onValueChange={(v) => updateParam("country", v)}
              >
                <SelectTrigger className="w-[160px]" aria-label="Filter by country">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {COUNTRY_OPTIONS.map((o) => (
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
                <SelectTrigger className="w-[160px]" aria-label="Filter by status">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {STATUS_OPTIONS.map((o) => (
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
            description="Couldn't load properties."
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
              <EmptyState
                title="No properties match these filters"
                description="Try clearing the search or changing the country/status filter."
              />
            }
          />
        )}
      </div>
    </div>
  );
}
