import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";
import type { SortingState } from "@tanstack/react-table";
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
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { orderingToSorting, sortingToOrdering } from "@/lib/drf/sorting";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { contactColumns } from "./columns";
import { useContacts } from "./hooks";
import { ContactFormDialog } from "./components/ContactFormDialog";
import type { ContactFilters, ContactListItem } from "./schemas";

const ALL_VALUE = "__all__";
const CONTACTS_PAGE_SIZE = 50;

function paramsToFilters(params: URLSearchParams): ContactFilters {
  const page = Number(params.get("page") ?? "1");
  return {
    q: params.get("q") ?? undefined,
    status: params.get("status") ?? undefined,
    ordering: params.get("ordering") ?? undefined,
    page: Number.isFinite(page) && page > 0 ? page : 1,
  };
}

export function ContactsListPage() {
  const { t } = useTranslation("contacts");
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  // Stringify-keyed memo: useSearchParams' URLSearchParams identity changes on every render.
  const filters = useMemo(() => paramsToFilters(params), [params.toString()]); // eslint-disable-line react-hooks/exhaustive-deps
  const [search, setSearch] = useState(filters.q ?? "");
  const [createOpen, setCreateOpen] = useState(false);
  const canWrite = useHasReservationsRole();

  const statusOptions = [
    { value: ALL_VALUE, label: t("status.any") },
    { value: "active", label: t("status.active") },
    { value: "inactive", label: t("status.inactive") },
    { value: "archived", label: t("status.archived") },
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

  const query = useContacts(filters);
  const pageCount = query.data ? Math.max(1, Math.ceil(query.data.count / CONTACTS_PAGE_SIZE)) : 1;
  const sorting = useMemo(() => orderingToSorting(filters.ordering), [filters.ordering]);

  const handleRowClick = (row: ContactListItem) => {
    navigate(`/contacts/${row.id}`);
  };

  const newButton = canWrite ? (
    <Button size="sm" onClick={() => setCreateOpen(true)}>
      {t("actions.new")}
    </Button>
  ) : (
    <Tooltip>
      <TooltipTrigger asChild>
        <span>
          <Button size="sm" disabled>
            {t("actions.new")}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>{t("tooltips.create_role_required")}</TooltipContent>
    </Tooltip>
  );

  return (
    <div>
      <PageHeader
        title={t("headings.list_title")}
        breadcrumbs={[{ label: t("headings.library") }, { label: t("headings.list_title") }]}
        actions={newButton}
      />
      <div className="space-y-4 p-6">
        <Toolbar
          searchValue={search}
          onSearchChange={setSearch}
          searchPlaceholder={t("placeholders.search")}
          filters={
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
          }
        />

        {query.isError ? (
          <ErrorState
            description={t("errors.load_failed")}
            onRetry={() => query.refetch()}
            retrying={query.isFetching}
          />
        ) : (
          <DataTable
            columns={contactColumns}
            data={query.data?.results}
            isLoading={query.isLoading}
            pageIndex={(filters.page ?? 1) - 1}
            pageCount={pageCount}
            pageSize={CONTACTS_PAGE_SIZE}
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

      {createOpen ? (
        <ContactFormDialog
          mode="create"
          open={createOpen}
          onOpenChange={setCreateOpen}
          onCreated={(c) => navigate(`/contacts/${c.id}`)}
        />
      ) : null}
    </div>
  );
}
