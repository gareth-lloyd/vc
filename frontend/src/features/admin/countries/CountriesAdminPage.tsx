import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { AdminPageShell } from "@/features/admin/components/AdminPageShell";
import { Toolbar } from "@/components/data/Toolbar";
import { DataTable } from "@/components/data/DataTable";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { MoreHorizontal } from "lucide-react";
import { useHasAdminRole } from "@/lib/auth/useHasAdminRole";
import { useCountries } from "@/lib/geo/hooks";
import { useDeleteCountry } from "./hooks";
import { countryColumns } from "./columns";
import { CountryFormDialog } from "./components/CountryFormDialog";
import type { Country } from "./schemas";

const PAGE_SIZE = 50;

interface CountryFilters {
  search?: string;
  page?: number;
}

function paramsToFilters(params: URLSearchParams): CountryFilters {
  const page = Number(params.get("page") ?? "1");
  return {
    search: params.get("q") ?? undefined,
    page: Number.isFinite(page) && page > 0 ? page : 1,
  };
}

export function CountriesAdminPage() {
  const { t } = useTranslation("admin");
  const [params, setParams] = useSearchParams();
  const filters = useMemo(() => paramsToFilters(params), [params.toString()]); // eslint-disable-line react-hooks/exhaustive-deps
  const [search, setSearch] = useState(filters.search ?? "");
  const [createOpen, setCreateOpen] = useState(false);
  const [editingCountry, setEditingCountry] = useState<Country | null>(null);
  const [deletingCountry, setDeletingCountry] = useState<Country | null>(null);
  const canWrite = useHasAdminRole();

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
          if (search) next.set("q", search);
          else next.delete("q");
          next.delete("page");
          return next;
        },
        { replace: true },
      );
    }, 250);
    return () => clearTimeout(handle);
  }, [search, filters.search, setParams]);

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

  const query = useCountries(filters);
  const pageCount = query.data ? Math.max(1, Math.ceil(query.data.count / PAGE_SIZE)) : 1;
  const columns = useMemo(() => countryColumns(t), [t]);

  return (
    <AdminPageShell
      title={t("countries.title")}
      description={t("countries.description")}
      actions={
        <Button size="sm" onClick={() => setCreateOpen(true)} disabled={!canWrite}>
          {t("countries.new_button")}
        </Button>
      }
    >
      <Toolbar
        searchValue={search}
        onSearchChange={setSearch}
        searchPlaceholder={t("countries.filters.search_placeholder")}
      />

      {query.isError ? (
        <ErrorState
          description={t("countries.errors.load_failed")}
          onRetry={() => query.refetch()}
          retrying={query.isFetching}
        />
      ) : (
        <DataTable
          columns={[
            ...columns,
            {
              id: "actions",
              header: "",
              enableSorting: false,
              cell: ({ row }) => (
                <RowActions
                  canWrite={canWrite}
                  onEdit={() => setEditingCountry(row.original)}
                  onDelete={() => setDeletingCountry(row.original)}
                />
              ),
            },
          ]}
          data={query.data?.results}
          isLoading={query.isLoading}
          pageIndex={(filters.page ?? 1) - 1}
          pageCount={pageCount}
          pageSize={PAGE_SIZE}
          sorting={[]}
          onSortingChange={() => {}}
          onPageChange={goToPage}
          rowKey={(row) => row.iso2}
          emptyContent={
            <EmptyState
              title={t("countries.empty.title")}
              description={t("countries.empty.description")}
            />
          }
        />
      )}

      {createOpen ? (
        <CountryFormDialog mode="create" open={createOpen} onOpenChange={setCreateOpen} />
      ) : null}
      {editingCountry ? (
        <CountryFormDialog
          mode="edit"
          country={editingCountry}
          open={editingCountry != null}
          onOpenChange={(o) => {
            if (!o) setEditingCountry(null);
          }}
        />
      ) : null}
      {deletingCountry ? (
        <DeleteCountryConfirm country={deletingCountry} onClose={() => setDeletingCountry(null)} />
      ) : null}
    </AdminPageShell>
  );
}

function RowActions({
  canWrite,
  onEdit,
  onDelete,
}: {
  canWrite: boolean;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const { t } = useTranslation("admin");
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          aria-label={t("users.row_actions.menu_label")}
          disabled={!canWrite}
        >
          <MoreHorizontal className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onSelect={onEdit}>{t("common.actions.edit")}</DropdownMenuItem>
        <DropdownMenuItem onSelect={onDelete} className="text-destructive">
          {t("common.actions.delete")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function DeleteCountryConfirm({ country, onClose }: { country: Country; onClose: () => void }) {
  const { t } = useTranslation("admin");
  const mutation = useDeleteCountry(country.iso2);
  const onConfirm = async () => {
    try {
      await mutation.mutateAsync();
      toast.success(t("countries.toasts.deleted"));
      onClose();
    } catch {
      toast.error(t("common:errors.generic"));
    }
  };
  return (
    <ConfirmDialog
      open
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
      onConfirm={onConfirm}
      title={t("countries.confirm_delete.title")}
      description={t("countries.confirm_delete.description")}
      confirmLabel={t("countries.confirm_delete.confirm")}
      busy={mutation.isPending}
      destructive
    />
  );
}
