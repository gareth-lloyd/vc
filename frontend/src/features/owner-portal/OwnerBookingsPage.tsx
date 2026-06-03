import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";
import type { SortingState } from "@tanstack/react-table";
import { PageHeader } from "@/components/layout/PageHeader";
import { DataTable } from "@/components/data/DataTable";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { orderingToSorting, sortingToOrdering } from "@/lib/drf/sorting";
import { useOwnerBookingColumns } from "./columns";
import { OWNER_BOOKINGS_PAGE_SIZE, useOwnerBookings } from "./hooks";
import type { OwnerBookingFilters, OwnerBookingListItem } from "./schemas";

function paramsToFilters(params: URLSearchParams): OwnerBookingFilters {
  const page = Number(params.get("page") ?? "1");
  return {
    ordering: params.get("ordering") ?? undefined,
    page: Number.isFinite(page) && page > 0 ? page : 1,
  };
}

export function OwnerBookingsPage() {
  const { t } = useTranslation("owner");
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  // Stringify-keyed memo: useSearchParams' URLSearchParams identity changes on every render.
  const filters = useMemo(() => paramsToFilters(params), [params.toString()]); // eslint-disable-line react-hooks/exhaustive-deps

  const query = useOwnerBookings(filters);
  const rows = query.data?.results;

  // The server omits rental_price for properties without a view_full_money
  // grant. Show the money column only when at least one visible row carries it.
  const showMoney = useMemo(() => (rows ?? []).some((r) => r.rental_price != null), [rows]);
  const columns = useOwnerBookingColumns(showMoney);

  const pageCount = query.data
    ? Math.max(1, Math.ceil(query.data.count / OWNER_BOOKINGS_PAGE_SIZE))
    : 1;
  const sorting = useMemo(() => orderingToSorting(filters.ordering), [filters.ordering]);

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

  const onSortingChange = (next: SortingState) => {
    setParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        const ordering = sortingToOrdering(next);
        if (ordering) params.set("ordering", ordering);
        else params.delete("ordering");
        params.delete("page");
        return params;
      },
      { replace: true },
    );
  };

  const handleRowClick = (row: OwnerBookingListItem) => {
    navigate(`/owner/bookings/${row.id}`);
  };

  return (
    <div>
      <PageHeader title={t("bookings.title")} subtitle={t("bookings.subtitle")} />
      <div className="space-y-4 p-6">
        {query.isError ? (
          <ErrorState description={t("bookings.load_failed")} onRetry={() => query.refetch()} />
        ) : (
          <DataTable
            columns={columns}
            data={rows}
            isLoading={query.isLoading}
            pageIndex={(filters.page ?? 1) - 1}
            pageCount={pageCount}
            pageSize={OWNER_BOOKINGS_PAGE_SIZE}
            sorting={sorting}
            onSortingChange={onSortingChange}
            onPageChange={goToPage}
            onRowClick={handleRowClick}
            rowKey={(row) => row.id}
            emptyContent={
              <EmptyState
                title={t("bookings.empty_title")}
                description={t("bookings.empty_hint")}
              />
            }
          />
        )}
      </div>
    </div>
  );
}
