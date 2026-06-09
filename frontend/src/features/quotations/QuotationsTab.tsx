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
import { orderingToSorting, sortingToOrdering } from "@/lib/drf/sorting";
import { buildQuotationColumns } from "./columns";
import { useQuotations, useQuotationStatusCounts, QUOTATIONS_PAGE_SIZE } from "./hooks";
import { quotationStatusOptions, type QuotationFilters, type QuotationListItem } from "./schemas";

const ALL_VALUE = "__all__";

function paramsToFilters(params: URLSearchParams): QuotationFilters {
  const page = Number(params.get("page") ?? "1");
  const enquiry = params.get("enquiry");
  return {
    q: params.get("q") ?? undefined,
    status: params.get("status") ?? undefined,
    enquiry: enquiry && /^\d+$/.test(enquiry) ? Number(enquiry) : undefined,
    ordering: params.get("ordering") ?? undefined,
    page: Number.isFinite(page) && page > 0 ? page : 1,
  };
}

/**
 * Cross-enquiry quotes pipeline, mounted as the "Quotes" tab under Enquiries
 * (`/enquiries/quotes`). Quote *creation* lives inline in the enquiry workspace,
 * so this is a read/triage surface — no standalone "new quote" affordance.
 */
export function QuotationsTab() {
  const { t } = useTranslation("quotations");
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  // useSearchParams' URLSearchParams identity changes every render — key the
  // memo on the serialized value, not the reference.
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

  const query = useQuotations(filters);
  const statusCounts = useQuotationStatusCounts(filters);
  const pageCount = query.data
    ? Math.max(1, Math.ceil(query.data.count / QUOTATIONS_PAGE_SIZE))
    : 1;
  const sorting = useMemo(() => orderingToSorting(filters.ordering), [filters.ordering]);
  const columns = useMemo(() => buildQuotationColumns(t), [t]);

  const handleRowClick = (row: QuotationListItem) => {
    navigate(`/quotations/${row.id}`);
  };

  return (
    <div>
      <PageHeader
        title={t("common:nav.quotes")}
        breadcrumbs={[
          // The tab strip below provides Enquiries↔Quotes navigation, so the
          // crumb trail stays flat (Operations / Quotes) rather than repeating
          // an "Enquiries" link.
          { label: t("common:nav.groups.operations") },
          { label: t("common:nav.quotes") },
        ]}
      />
      <div className="space-y-4 p-6">
        <StatusFilterBar
          options={quotationStatusOptions()}
          counts={statusCounts.data}
          value={filters.status}
          onChange={(v) => updateParam("status", v)}
          allLabel={t("common:status_filter.all")}
        />
        <Toolbar
          searchValue={search}
          onSearchChange={setSearch}
          searchPlaceholder={t("list.search_placeholder")}
        />

        {query.isError ? (
          <ErrorState
            description={t("list.errors.load_failed")}
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
            pageSize={QUOTATIONS_PAGE_SIZE}
            sorting={sorting}
            onSortingChange={onSortingChange}
            onPageChange={goToPage}
            onRowClick={handleRowClick}
            rowKey={(row) => row.id}
            emptyContent={
              <EmptyState title={t("list.empty.title")} description={t("list.empty.description")} />
            }
          />
        )}
      </div>
    </div>
  );
}
