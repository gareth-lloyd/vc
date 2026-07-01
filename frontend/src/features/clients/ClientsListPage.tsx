import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";
import type { SortingState } from "@tanstack/react-table";
import { PageHeader } from "@/components/layout/PageHeader";
import { Toolbar } from "@/components/data/Toolbar";
import { DataTable } from "@/components/data/DataTable";
import { Badge } from "@/components/ui/badge";
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
import { PERSON_TAGS } from "@/features/contacts/personTags";
import { clientColumns } from "./columns";
import { useClients } from "./hooks";
import type { ClientFilters, ClientListItem } from "./schemas";

const ALL_VALUE = "__all__";
const CLIENTS_PAGE_SIZE = 50;

// The two customer tags surfaced as one-click chips (a deliberate subset of the
// full PERSON_TAGS taxonomy). Defines the canonical order the `tags` overlap
// param is written in, so click order never changes the URL or React Query key.
// Validated against the canonical taxonomy so a token can't silently drift to
// one the backend would ignore.
const TAG_CHIP_VALUES: readonly string[] = ["vip", "trade"];
if (import.meta.env.DEV) {
  const known = new Set(PERSON_TAGS.map((tag) => tag.value));
  const unknown = TAG_CHIP_VALUES.filter((value) => !known.has(value));
  if (unknown.length) throw new Error(`Unknown client tag chip(s): ${unknown.join(", ")}`);
}

// Rewrite a tag set into canonical (chip-definition) order: known chip tags
// first, any hand-URL'd extras after, so the param is stable regardless of how
// it was assembled.
function canonicalTags(tags: Iterable<string>): string[] {
  const set = new Set(tags);
  const known = TAG_CHIP_VALUES.filter((value) => set.has(value));
  const extra = [...set].filter((value) => !TAG_CHIP_VALUES.includes(value)).sort();
  return [...known, ...extra];
}

function paramsToFilters(params: URLSearchParams): ClientFilters {
  const page = Number(params.get("page") ?? "1");
  return {
    search: params.get("search") ?? undefined,
    status: params.get("status") ?? undefined,
    capacity: params.get("capacity") ?? undefined,
    tags: params.get("tags") ?? undefined,
    repeat: params.get("repeat") === "true" ? true : undefined,
    ordering: params.get("ordering") ?? undefined,
    page: Number.isFinite(page) && page > 0 ? page : 1,
  };
}

export function ClientsListPage() {
  const { t } = useTranslation("clients");
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  // Stringify-keyed memo: useSearchParams' URLSearchParams identity changes on every render.
  const filters = useMemo(() => paramsToFilters(params), [params.toString()]); // eslint-disable-line react-hooks/exhaustive-deps
  const [search, setSearch] = useState(filters.search ?? "");

  const statusOptions = [
    { value: ALL_VALUE, label: t("status.any") },
    { value: "active", label: t("status.active") },
    { value: "inactive", label: t("status.inactive") },
  ];
  const capacityOptions = [
    { value: ALL_VALUE, label: t("capacity.any") },
    { value: "direct", label: t("capacity.direct") },
    { value: "agent", label: t("capacity.agent") },
  ];

  useEffect(() => {
    setSearch(filters.search ?? "");
  }, [filters.search]);

  useEffect(() => {
    const current = filters.search ?? "";
    if (search === current) return;
    const handle = setTimeout(() => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (search) next.set("search", search);
          else next.delete("search");
          next.delete("page");
          return next;
        },
        { replace: true },
      );
    }, 250);
    return () => clearTimeout(handle);
  }, [search, filters.search, setParams]);

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

  // GAP-053 quick-filter chips. VIP/Trade toggle membership in the comma-joined
  // `tags` overlap param; Repeat toggles the boolean `repeat` flag. All compose
  // with search/capacity/status (each just edits its own param).
  const activeTags = (filters.tags ?? "").split(",").filter(Boolean);
  const toggleTag = (tag: string) => {
    const set = new Set(activeTags);
    if (set.has(tag)) set.delete(tag);
    else set.add(tag);
    const next = canonicalTags(set);
    updateParam("tags", next.length ? next.join(",") : undefined);
  };
  const filterChips = [
    {
      key: "vip",
      label: t("chips.vip"),
      active: activeTags.includes("vip"),
      toggle: () => toggleTag("vip"),
    },
    {
      key: "trade",
      label: t("chips.trade"),
      active: activeTags.includes("trade"),
      toggle: () => toggleTag("trade"),
    },
    {
      key: "repeat",
      label: t("chips.repeat"),
      active: Boolean(filters.repeat),
      toggle: () => updateParam("repeat", filters.repeat ? undefined : "true"),
    },
  ];

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

  const query = useClients(filters);
  const pageCount = query.data ? Math.max(1, Math.ceil(query.data.count / CLIENTS_PAGE_SIZE)) : 1;
  const sorting = useMemo(() => orderingToSorting(filters.ordering), [filters.ordering]);

  // List-only directory: rows open the existing contact detail until GAP-042
  // builds the customer-360 profile.
  const handleRowClick = (row: ClientListItem) => {
    navigate(`/contacts/${row.id}`);
  };

  return (
    <div>
      <PageHeader
        title={t("headings.list_title")}
        breadcrumbs={[{ label: t("headings.library") }, { label: t("headings.list_title") }]}
      />
      <div className="space-y-4 p-6">
        <Toolbar
          searchValue={search}
          onSearchChange={setSearch}
          searchPlaceholder={t("placeholders.search")}
          filters={
            <>
              <Select
                value={filters.capacity ?? ALL_VALUE}
                onValueChange={(v) => updateParam("capacity", v)}
              >
                <SelectTrigger className="w-[160px]" aria-label={t("filters.filter_capacity_aria")}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {capacityOptions.map((o) => (
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
                <SelectTrigger className="w-[160px]" aria-label={t("filters.filter_status_aria")}>
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

        <div
          role="group"
          className="flex flex-wrap items-center gap-2"
          aria-label={t("filters.quick_chips_aria")}
        >
          {filterChips.map((chip) => (
            <button
              key={chip.key}
              type="button"
              onClick={chip.toggle}
              aria-pressed={chip.active}
              className="focus-visible:ring-ring rounded-full focus-visible:ring-2 focus-visible:outline-none"
            >
              <Badge variant={chip.active ? "default" : "outline"} className="cursor-pointer">
                {chip.label}
              </Badge>
            </button>
          ))}
        </div>

        {query.isError ? (
          <ErrorState
            description={t("errors.load_failed")}
            onRetry={() => query.refetch()}
            retrying={query.isFetching}
          />
        ) : (
          <DataTable
            columns={clientColumns}
            data={query.data?.results}
            isLoading={query.isLoading}
            pageIndex={(filters.page ?? 1) - 1}
            pageCount={pageCount}
            pageSize={CLIENTS_PAGE_SIZE}
            sorting={sorting}
            onSortingChange={onSortingChange}
            onPageChange={goToPage}
            onRowClick={handleRowClick}
            rowKey={(row) => row.id}
            emptyContent={
              <EmptyState title={t("empty.list_title")} description={t("empty.list_hint")} />
            }
          />
        )}
      </div>
    </div>
  );
}
