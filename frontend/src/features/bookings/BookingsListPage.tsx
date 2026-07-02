import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";
import type { SortingState } from "@tanstack/react-table";
import { PageHeader } from "@/components/layout/PageHeader";
import { Toolbar } from "@/components/data/Toolbar";
import { StatusFilterBar } from "@/components/data/StatusFilterBar";
import { DataTable } from "@/components/data/DataTable";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { UncontrolledDateRangePicker } from "@/components/form/UncontrolledDateRangePicker";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { CheckboxLabel } from "@/components/ui/checkbox-label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { orderingToSorting, sortingToOrdering } from "@/lib/drf/sorting";
import { useBookingColumns } from "./columns";
import { BOOKINGS_PAGE_SIZE, useBookings, useBookingStatusCounts } from "./hooks";
import {
  bookingStatusOptions,
  bookingStatusSchema,
  type BookingFilters,
  type BookingListItem,
  type BookingStatus,
} from "./schemas";

const ALL_VALUE = "__all__";

const SITE_VALUES = ["main_website", "owner_referral", "phone", "email", "manual"] as const;

function parseStatus(value: string | null): BookingStatus | undefined {
  if (!value) return undefined;
  const parsed = bookingStatusSchema.safeParse(value);
  return parsed.success ? parsed.data : undefined;
}

function paramsToFilters(params: URLSearchParams): BookingFilters {
  const page = Number(params.get("page") ?? "1");
  return {
    q: params.get("q") ?? undefined,
    status: parseStatus(params.get("status")),
    site: params.get("site") ?? undefined,
    ordering: params.get("ordering") ?? undefined,
    page: Number.isFinite(page) && page > 0 ? page : 1,
    check_in_after: params.get("check_in_after") ?? undefined,
    check_in_before: params.get("check_in_before") ?? undefined,
    check_out_after: params.get("check_out_after") ?? undefined,
    check_out_before: params.get("check_out_before") ?? undefined,
    exclude_terminal: params.get("exclude_terminal") === "true" || undefined,
  };
}

export function BookingsListPage() {
  const { t } = useTranslation("bookings");
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  // Stringify-keyed memo: useSearchParams' URLSearchParams identity changes on every render.
  const filters = useMemo(() => paramsToFilters(params), [params.toString()]); // eslint-disable-line react-hooks/exhaustive-deps
  const [search, setSearch] = useState(filters.q ?? "");
  const columns = useBookingColumns();

  const statusOptions = useMemo(() => bookingStatusOptions(), []);
  const siteOptions = useMemo(
    () => [
      { value: ALL_VALUE, label: t("filters.any_source") },
      ...SITE_VALUES.map((value) => ({ value, label: t(`source.${value}`) })),
    ],
    [t],
  );

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

  // Writes a check-in / check-out range as one atomic history entry (one
  // refetch). The picker emits the full latest pair on every edit, so setting
  // both keys from `prev` each time is correct (latest-wins).
  const applyRange = (afterKey: string, beforeKey: string) => (from: string, to: string) => {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (from) next.set(afterKey, from);
        else next.delete(afterKey);
        if (to) next.set(beforeKey, to);
        else next.delete(beforeKey);
        next.delete("page");
        return next;
      },
      { replace: true },
    );
  };

  // Clears every filter but keeps the sort (Clear *filters*, not the ordering).
  const clearAllFilters = () => {
    setSearch("");
    setParams(
      (prev) => {
        const next = new URLSearchParams();
        const ordering = prev.get("ordering");
        if (ordering) next.set("ordering", ordering);
        return next;
      },
      { replace: true },
    );
  };

  // `search` (a superset of `filters.q` — it leads during the 250ms debounce)
  // so the affordance appears the moment the user starts typing.
  const hasActiveFilters = Boolean(
    filters.status ||
    filters.site ||
    filters.check_in_after ||
    filters.check_in_before ||
    filters.check_out_after ||
    filters.check_out_before ||
    filters.exclude_terminal ||
    search,
  );

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

  const query = useBookings(filters);
  const statusCounts = useBookingStatusCounts(filters);
  const pageCount = query.data ? Math.max(1, Math.ceil(query.data.count / BOOKINGS_PAGE_SIZE)) : 1;
  const sorting = useMemo(() => orderingToSorting(filters.ordering), [filters.ordering]);

  const handleRowClick = (row: BookingListItem) => {
    navigate(`/bookings/${row.id}/overview`);
  };

  return (
    <div>
      <PageHeader
        title={t("list.title")}
        breadcrumbs={[
          { label: t("list.breadcrumb_operations") },
          { label: t("list.breadcrumb_bookings") },
        ]}
      />
      <div className="space-y-4 p-6">
        <StatusFilterBar
          options={statusOptions}
          counts={statusCounts.data}
          value={filters.status}
          onChange={(v) => updateParam("status", v)}
          allLabel={t("common:status_filter.all")}
        />
        <Toolbar
          searchValue={search}
          onSearchChange={setSearch}
          searchPlaceholder={t("list.search_placeholder")}
          filters={
            <>
              <Select
                value={filters.site ?? ALL_VALUE}
                onValueChange={(v) => updateParam("site", v)}
              >
                <SelectTrigger className="w-[160px]" aria-label={t("list.filter_source_aria")}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {siteOptions.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </>
          }
        />

        <div className="flex flex-wrap items-end gap-3">
          {/* Bounded width keeps each w-full trigger from stretching the row. */}
          <div className="w-64">
            <UncontrolledDateRangePicker
              id="booking-check-in"
              mode="days"
              label={t("filters.check_in")}
              fromLabel={t("filters.from")}
              toLabel={t("filters.to")}
              value={{ from: filters.check_in_after ?? "", to: filters.check_in_before ?? "" }}
              onChange={applyRange("check_in_after", "check_in_before")}
            />
          </div>
          <div className="w-64">
            <UncontrolledDateRangePicker
              id="booking-check-out"
              mode="days"
              label={t("filters.check_out")}
              fromLabel={t("filters.from")}
              toLabel={t("filters.to")}
              value={{ from: filters.check_out_after ?? "", to: filters.check_out_before ?? "" }}
              onChange={applyRange("check_out_after", "check_out_before")}
            />
          </div>
          <CheckboxLabel className="h-9">
            <Checkbox
              checked={!!filters.exclude_terminal}
              onCheckedChange={(c) =>
                updateParam("exclude_terminal", c === true ? "true" : undefined)
              }
            />
            {t("filters.exclude_terminal")}
          </CheckboxLabel>
          {hasActiveFilters ? (
            <Button variant="ghost" size="sm" className="h-9" onClick={clearAllFilters}>
              {t("filters.clear_all")}
            </Button>
          ) : null}
        </div>

        {query.isError ? (
          <ErrorState
            description={t("list.load_failed")}
            onRetry={() => query.refetch()}
            retrying={query.isFetching}
          />
        ) : (
          <DataTable
            columns={columns}
            data={query.data?.results}
            isLoading={query.isLoading}
            pageIndex={(filters.page ?? 1) - 1}
            pageCount={pageCount}
            pageSize={BOOKINGS_PAGE_SIZE}
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
    </div>
  );
}
