import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { SortingState } from "@tanstack/react-table";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/PageHeader";
import { Toolbar } from "@/components/data/Toolbar";
import { DataTable } from "@/components/data/DataTable";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { orderingToSorting, sortingToOrdering } from "@/lib/drf/sorting";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { ApiError } from "@/lib/api/errors";
import { useEnquiryColumns } from "./columns";
import { ENQUIRIES_PAGE_SIZE, useEnquiries, useMoveEnquiry } from "./hooks";
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

const ALL_VALUE = "__all__";

type ViewMode = "kanban" | "list";

function parseStatus(value: string | null): EnquiryStatus | undefined {
  if (!value) return undefined;
  const parsed = enquiryStatusSchema.safeParse(value);
  return parsed.success ? parsed.data : undefined;
}

function parseView(value: string | null): ViewMode {
  return value === "list" ? "list" : "kanban";
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
  const [params, setParams] = useSearchParams();
  const filters = useMemo(() => paramsToFilters(params), [params.toString()]); // eslint-disable-line react-hooks/exhaustive-deps
  const view: ViewMode = parseView(params.get("view"));
  const [search, setSearch] = useState(filters.q ?? "");
  const [createOpen, setCreateOpen] = useState(false);

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

  const setView = (next: ViewMode) => {
    setParams(
      (prev) => {
        const out = new URLSearchParams(prev);
        if (next === "list") out.set("view", "list");
        else out.delete("view");
        return out;
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

  const query = useEnquiries(filters);
  const moveMutation = useMoveEnquiry();
  const enquiryColumns = useEnquiryColumns();
  const pageCount = query.data ? Math.max(1, Math.ceil(query.data.count / ENQUIRIES_PAGE_SIZE)) : 1;
  const sorting = useMemo(() => orderingToSorting(filters.ordering), [filters.ordering]);

  const statusOptions = [
    { value: ALL_VALUE, label: t("list.any_status") },
    ...enquiryStatusOptions(),
  ];

  const handleRowClick = (row: EnquiryListItem) => {
    navigate(`/enquiries/${row.id}/details`);
  };

  const handleMove = (itemId: string, _fromColId: string, toColId: string) => {
    const enquiry = query.data?.results.find((e) => String(e.id) === itemId);
    if (!enquiry) return;
    const target = enquiryStatusSchema.safeParse(toColId);
    if (!target.success) return;
    // Only `lost` and `new` (reopen) are directly drag-targetable; the other
    // transitions need extra data (assigned operator, quotation id) so we
    // surface them via the detail page actions.
    if (target.data !== "lost" && target.data !== "new") {
      toast.info(t("list.toasts.move_blocked"));
      return;
    }
    moveMutation.mutate(
      { enquiry, toStatus: target.data },
      {
        onError: () => {
          toast.error(t("list.toasts.move_failed", { reference: enquiry.reference }));
          void query.refetch();
        },
        onSuccess: () => {
          toast.success(
            t("list.toasts.move_success", {
              reference: enquiry.reference,
              status: enquiryStatusLabel(target.data),
            }),
          );
        },
      },
    );
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
        <Toolbar
          searchValue={search}
          onSearchChange={setSearch}
          searchPlaceholder={t("list.search_placeholder")}
          filters={
            <>
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
                <EnquiryCard
                  enquiry={item}
                  onClick={() => navigate(`/enquiries/${item.id}/details`)}
                />
              )}
              onMoveItem={handleMove}
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
