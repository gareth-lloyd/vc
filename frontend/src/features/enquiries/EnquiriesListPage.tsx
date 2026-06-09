import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { SortingState } from "@tanstack/react-table";
import { PageHeader } from "@/components/layout/PageHeader";
import { Toolbar } from "@/components/data/Toolbar";
import { StatusFilterBar } from "@/components/data/StatusFilterBar";
import { DataTable } from "@/components/data/DataTable";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { orderingToSorting, sortingToOrdering } from "@/lib/drf/sorting";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { useListParams } from "@/lib/list/useListParams";
import { ApiError } from "@/lib/api/errors";
import { useEnquiryColumns } from "./columns";
import { ENQUIRIES_PAGE_SIZE, useEnquiries, useEnquiryStatusCounts } from "./hooks";
import { EnquiryCard } from "./components/EnquiryCard";
import { KanbanBoard, type KanbanColumn } from "./components/KanbanBoard";
import { EnquiryFormDialog } from "./components/EnquiryFormDialog";
import {
  KANBAN_STATUSES,
  enquiryStatusLabel,
  enquiryStatusOptions,
  enquiryStatusSchema,
  type EnquiryFilters,
  type EnquiryListItem,
  type EnquiryStatus,
} from "./schemas";

type ViewMode = "kanban" | "list";

function parseStatus(value: string | null): EnquiryStatus | undefined {
  if (!value) return undefined;
  const parsed = enquiryStatusSchema.safeParse(value);
  return parsed.success ? parsed.data : undefined;
}

function parseView(value: string | null, hasStatusFilter: boolean): ViewMode {
  if (value === "list" || value === "kanban") return value;
  // When the user lands with an explicit ?status= filter (e.g. from the dashboard),
  // the Kanban's all-columns layout would hide that filter — prefer the list view.
  return hasStatusFilter ? "list" : "kanban";
}

function paramsToFilters(params: URLSearchParams): EnquiryFilters {
  const page = Number(params.get("page") ?? "1");
  return {
    q: params.get("q") ?? undefined,
    status: parseStatus(params.get("status")),
    ordering: params.get("ordering") ?? undefined,
    page: Number.isFinite(page) && page > 0 ? page : 1,
  };
}

function groupIntoColumns(
  items: EnquiryListItem[],
  titleFor: (status: EnquiryStatus) => string,
): KanbanColumn<EnquiryListItem>[] {
  const buckets: Record<EnquiryStatus, EnquiryListItem[]> = {
    new: [],
    contacted: [],
    quoted: [],
    converted: [],
    lost: [],
  };
  for (const item of items) {
    buckets[item.status]?.push(item);
  }
  return KANBAN_STATUSES.map((status) => ({
    id: status,
    title: titleFor(status),
    items: buckets[status],
  }));
}

export function EnquiriesListPage() {
  const { t } = useTranslation("enquiries");
  const navigate = useNavigate();
  const hasRole = useHasReservationsRole();
  const { params, setParams, search, setSearch, updateParam, goToPage } = useListParams();
  const filters = useMemo(() => paramsToFilters(params), [params.toString()]); // eslint-disable-line react-hooks/exhaustive-deps
  const view: ViewMode = parseView(params.get("view"), filters.status !== undefined);
  const [createOpen, setCreateOpen] = useState(false);

  const setView = (next: ViewMode) => {
    setParams(
      (prev) => {
        const out = new URLSearchParams(prev);
        // Always write the chosen value: with a `?status=` filter present the
        // implicit default flips to "list", so an explicit Kanban click would
        // otherwise be a no-op if we only stored the non-default branch.
        out.set("view", next);
        return out;
      },
      { replace: true },
    );
  };

  const onSortingChange = (sorting: SortingState) => {
    updateParam("ordering", sortingToOrdering(sorting));
  };

  // The Kanban shows every status as a column and has no filter UI, so a
  // lingering `?status=` (e.g. from a dashboard deep-link) would silently empty
  // most columns. Drop it for the board query; the URL param is preserved for
  // when the user switches back to the list view (where the bar shows it).
  const effectiveFilters = view === "kanban" ? { ...filters, status: undefined } : filters;
  const query = useEnquiries(effectiveFilters);
  const statusCounts = useEnquiryStatusCounts(filters);
  const enquiryColumns = useEnquiryColumns();
  const pageCount = query.data ? Math.max(1, Math.ceil(query.data.count / ENQUIRIES_PAGE_SIZE)) : 1;
  const sorting = useMemo(() => orderingToSorting(filters.ordering), [filters.ordering]);

  const statusOptions = useMemo(() => enquiryStatusOptions(), []);

  const handleRowClick = (row: EnquiryListItem) => {
    navigate(`/enquiries/${row.id}`);
  };

  const newButton = (
    <Button onClick={() => setCreateOpen(true)} disabled={!hasRole}>
      {t("list.new_button")}
    </Button>
  );

  return (
    <div>
      <PageHeader
        title={t("list.title")}
        breadcrumbs={[
          { label: t("list.breadcrumb_operations") },
          { label: t("list.breadcrumb_enquiries") },
        ]}
      />
      <div className="space-y-4 p-6">
        {view === "list" ? (
          <StatusFilterBar
            options={statusOptions}
            counts={statusCounts.data}
            value={filters.status}
            onChange={(v) => updateParam("status", v)}
            allLabel={t("common:status_filter.all")}
          />
        ) : null}
        <Toolbar
          searchValue={search}
          onSearchChange={setSearch}
          searchPlaceholder={t("list.search_placeholder")}
          filters={
            <>
              <div
                role="tablist"
                aria-label={t("list.view_aria")}
                className="border-border inline-flex overflow-hidden rounded-md border"
              >
                <button
                  type="button"
                  role="tab"
                  aria-selected={view === "kanban"}
                  onClick={() => setView("kanban")}
                  className={
                    view === "kanban"
                      ? "bg-foreground text-background px-3 py-1.5 text-sm"
                      : "text-muted-foreground px-3 py-1.5 text-sm"
                  }
                >
                  {t("list.view_kanban")}
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={view === "list"}
                  onClick={() => setView("list")}
                  className={
                    view === "list"
                      ? "bg-foreground text-background px-3 py-1.5 text-sm"
                      : "text-muted-foreground px-3 py-1.5 text-sm"
                  }
                >
                  {t("list.view_list")}
                </button>
              </div>
            </>
          }
          rightSlot={
            hasRole ? (
              newButton
            ) : (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="block">{newButton}</span>
                </TooltipTrigger>
                <TooltipContent>{t("common:errors.reservations_role_required")}</TooltipContent>
              </Tooltip>
            )
          }
        />

        {query.isError ? (
          <ErrorState
            description={
              query.error instanceof ApiError
                ? t("list.load_failed_status", { status: query.error.status })
                : t("list.load_failed")
            }
            onRetry={() => query.refetch()}
            retrying={query.isFetching}
          />
        ) : view === "kanban" ? (
          query.isLoading ? (
            <Skeleton className="h-96 w-full" />
          ) : (
            <KanbanBoard<EnquiryListItem>
              columns={groupIntoColumns(query.data?.results ?? [], enquiryStatusLabel)}
              getItemId={(item) => String(item.id)}
              renderCard={(item) => (
                <EnquiryCard enquiry={item} onClick={() => navigate(`/enquiries/${item.id}`)} />
              )}
            />
          )
        ) : (
          <DataTable
            columns={enquiryColumns}
            data={query.data?.results}
            isLoading={query.isLoading}
            pageIndex={(filters.page ?? 1) - 1}
            pageCount={pageCount}
            pageSize={ENQUIRIES_PAGE_SIZE}
            sorting={sorting}
            onSortingChange={onSortingChange}
            onPageChange={goToPage}
            onRowClick={handleRowClick}
            rowKey={(row) => row.id}
            emptyContent={
              <EmptyState title={t("list.empty_title")} description={t("list.empty_body")} />
            }
          />
        )}
      </div>

      {createOpen && (
        <EnquiryFormDialog mode="create" open={createOpen} onOpenChange={setCreateOpen} />
      )}
    </div>
  );
}
