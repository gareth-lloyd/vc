import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
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
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { orderingToSorting, sortingToOrdering } from "@/lib/drf/sorting";
import { buildQuotationColumns } from "./columns";
import { useQuotations, QUOTATIONS_PAGE_SIZE } from "./hooks";
import {
  QUOTATION_STATUS_LABELS,
  QUOTATION_STATUS_OPTIONS,
  type QuotationFilters,
  type QuotationListItem,
  type QuotationStatus,
} from "./schemas";

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

export function QuotationsListPage() {
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
  const pageCount = query.data
    ? Math.max(1, Math.ceil(query.data.count / QUOTATIONS_PAGE_SIZE))
    : 1;
  const sorting = useMemo(() => orderingToSorting(filters.ordering), [filters.ordering]);
  const columns = useMemo(() => buildQuotationColumns(t), [t]);

  const handleRowClick = (row: QuotationListItem) => {
    navigate(`/quotations/${row.id}`);
  };

  const newButton = (
    <Tooltip>
      <TooltipTrigger asChild>
        <span>
          <Button size="sm" disabled>
            {t("list.coming_soon.new_button")}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>{t("list.coming_soon.tooltip")}</TooltipContent>
    </Tooltip>
  );

  return (
    <div>
      <PageHeader
        title={t("list.title")}
        breadcrumbs={[{ label: t("list.breadcrumb_root") }, { label: t("list.breadcrumb_self") }]}
        actions={newButton}
      />
      <div className="space-y-4 p-6">
        <Toolbar
          searchValue={search}
          onSearchChange={setSearch}
          searchPlaceholder={t("list.search_placeholder")}
          filters={
            <Select
              value={filters.status ?? ALL_VALUE}
              onValueChange={(v) => updateParam("status", v)}
            >
              <SelectTrigger className="w-[160px]" aria-label={t("list.filters.status_label")}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL_VALUE}>{t("list.filters.status_any")}</SelectItem>
                {QUOTATION_STATUS_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {QUOTATION_STATUS_LABELS[o.value as QuotationStatus]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          }
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
