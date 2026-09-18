import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import type { ColumnDef, SortingState } from "@tanstack/react-table";
import { DataTable } from "@/components/data/DataTable";
import { Toolbar } from "@/components/data/Toolbar";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { importedBookingWhen, recordedAmount } from "@/lib/domain/importedBooking";
import { BOOKINGS_PAGE_SIZE, useImportedBookings } from "../hooks";
import type { ImportedBookingFilters, ImportedBookingListItem } from "../schemas";

// The list keeps the backend's order (newest year first) and offers no sort.
const NO_SORT: SortingState = [];
const ignoreSort = () => {};

const MUTED_DASH = <span className="text-muted-foreground">—</span>;

function paramsToFilters(params: URLSearchParams): ImportedBookingFilters {
  const page = Number(params.get("page") ?? "1");
  return {
    q: params.get("q") ?? undefined,
    page: Number.isFinite(page) && page > 0 ? page : 1,
  };
}

function useImportedBookingColumns(): ColumnDef<ImportedBookingListItem>[] {
  const { t } = useTranslation("bookings");
  return useMemo<ColumnDef<ImportedBookingListItem>[]>(
    () => [
      {
        id: "guest",
        header: t("imported.columns.guest"),
        enableSorting: false,
        cell: ({ row }) => (
          <Link
            to={`/clients/${row.original.person}/details`}
            className="hover:text-primary text-sm hover:underline"
          >
            {row.original.person_name ?? t("imported.unnamed_client")}
          </Link>
        ),
      },
      {
        id: "villa",
        header: t("imported.columns.villa"),
        enableSorting: false,
        // The resolved property when the importer matched the sheet's villa
        // name; otherwise the name exactly as written.
        cell: ({ row }) => {
          const { property, property_name, villa_name } = row.original;
          return property != null ? (
            <Link
              to={`/properties/${property}`}
              className="hover:text-primary text-sm hover:underline"
            >
              {property_name ?? villa_name}
            </Link>
          ) : (
            <span className="text-sm">{villa_name}</span>
          );
        },
      },
      {
        id: "destination",
        header: t("imported.columns.destination"),
        enableSorting: false,
        cell: ({ row }) =>
          row.original.destination ? (
            <span className="text-sm">{row.original.destination}</span>
          ) : (
            MUTED_DASH
          ),
      },
      {
        id: "when",
        header: t("imported.columns.when"),
        enableSorting: false,
        cell: ({ row }) => (
          <span className="text-sm">
            {importedBookingWhen(row.original) ?? t("imported.year_unknown")}
          </span>
        ),
      },
      {
        id: "booking_number",
        header: t("imported.columns.booking_number"),
        enableSorting: false,
        cell: ({ row }) =>
          row.original.booking_number ? (
            <span className="font-mono text-sm">{row.original.booking_number}</span>
          ) : (
            MUTED_DASH
          ),
      },
      {
        id: "amount",
        header: t("imported.columns.amount"),
        enableSorting: false,
        cell: ({ row }) => {
          const amount = recordedAmount(row.original);
          return amount ? <span className="text-sm tabular-nums">{amount}</span> : MUTED_DASH;
        },
      },
    ],
    [t],
  );
}

/**
 * GAP-117: the "Imported bookings" tab on /bookings — historic stays loaded
 * once from the legacy system (backend `PastStay`), across all clients.
 * Read-only: search + pagination only; rows link to the client and villa.
 * Never lists a booking made in this app. Owns the `q` / `page` URL params.
 */
export function ImportedBookingsTab() {
  const { t } = useTranslation("bookings");
  const [params, setParams] = useSearchParams();
  // Stringify-keyed memo: useSearchParams' URLSearchParams identity changes on every render.
  const filters = useMemo(() => paramsToFilters(params), [params.toString()]); // eslint-disable-line react-hooks/exhaustive-deps
  const [search, setSearch] = useState(filters.q ?? "");
  const columns = useImportedBookingColumns();

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

  const query = useImportedBookings(filters);
  const pageCount = query.data ? Math.max(1, Math.ceil(query.data.count / BOOKINGS_PAGE_SIZE)) : 1;

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground text-sm">{t("imported.description")}</p>
      <Toolbar
        searchValue={search}
        onSearchChange={setSearch}
        searchPlaceholder={t("imported.search_placeholder")}
      />
      {query.isError ? (
        <ErrorState
          description={t("imported.load_failed")}
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
          sorting={NO_SORT}
          onSortingChange={ignoreSort}
          onPageChange={goToPage}
          rowKey={(row) => row.id}
          emptyContent={
            <EmptyState title={t("imported.empty_title")} description={t("imported.empty_hint")} />
          }
        />
      )}
    </div>
  );
}
