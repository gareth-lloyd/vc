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
import { contactColumns, supplierColumns } from "./columns";
import { useContacts } from "./hooks";
import { ContactFormDialog } from "./components/ContactFormDialog";
import type { ContactFilters, ContactListItem } from "./schemas";

const ALL_VALUE = "__all__";
const CONTACTS_PAGE_SIZE = 50;

interface ContactsListPageProps {
  // GAP-048: `directory="suppliers"` is the Suppliers nav surface — it pins
  // `?directory=suppliers` on the query (operator-side, kind=CONTACT minus
  // agent-capacity), swaps the kind column for a property-role column, hides the
  // now-redundant kind filter, and relabels the heading/empty copy. Omitted →
  // the unscoped contacts directory.
  directory?: "suppliers";
}

function paramsToFilters(params: URLSearchParams): ContactFilters {
  const page = Number(params.get("page") ?? "1");
  return {
    q: params.get("q") ?? undefined,
    status: params.get("status") ?? undefined,
    kind: params.get("kind") ?? undefined,
    ordering: params.get("ordering") ?? undefined,
    page: Number.isFinite(page) && page > 0 ? page : 1,
  };
}

export function ContactsListPage({ directory }: ContactsListPageProps = {}) {
  const { t } = useTranslation("contacts");
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const isSuppliers = directory === "suppliers";
  const title = isSuppliers ? t("headings.suppliers_title") : t("headings.list_title");
  // Stringify-keyed memo: useSearchParams' URLSearchParams identity changes on every render.
  const filters = useMemo(
    // On the suppliers surface the kind filter UI is hidden, so a stale
    // `?kind=` in the URL would silently AND with the forced kind=CONTACT and
    // empty the list with no affordance to clear it — drop it.
    () =>
      isSuppliers
        ? { ...paramsToFilters(params), kind: undefined, directory: "suppliers" }
        : paramsToFilters(params),
    [params.toString(), isSuppliers], // eslint-disable-line react-hooks/exhaustive-deps
  );
  const [search, setSearch] = useState(filters.q ?? "");
  const [createOpen, setCreateOpen] = useState(false);
  const canWrite = useHasReservationsRole();

  const kindOptions = [
    { value: ALL_VALUE, label: t("kind.any") },
    { value: "customer", label: t("kind.customer") },
    { value: "contact", label: t("kind.contact") },
  ];

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
        title={title}
        breadcrumbs={[{ label: t("headings.library") }, { label: title }]}
        actions={newButton}
      />
      <div className="space-y-4 p-6">
        <Toolbar
          searchValue={search}
          onSearchChange={setSearch}
          searchPlaceholder={t("placeholders.search")}
          filters={
            <>
              {/* The kind filter is redundant on the suppliers-scoped list (all
                  rows are kind=CONTACT) — hidden there. */}
              {!isSuppliers ? (
                <Select
                  value={filters.kind ?? ALL_VALUE}
                  onValueChange={(v) => updateParam("kind", v)}
                >
                  <SelectTrigger className="w-[160px]" aria-label={t("filters.filter_kind_aria")}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {kindOptions.map((o) => (
                      <SelectItem key={o.value} value={o.value}>
                        {o.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : null}
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

        {query.isError ? (
          <ErrorState
            description={t("errors.load_failed")}
            onRetry={() => query.refetch()}
            retrying={query.isFetching}
          />
        ) : (
          <DataTable
            columns={isSuppliers ? supplierColumns : contactColumns}
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
              <EmptyState
                title={isSuppliers ? t("empty.suppliers_title") : t("empty.list_title")}
                description={isSuppliers ? t("empty.suppliers_hint") : t("empty.list_hint")}
              />
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
