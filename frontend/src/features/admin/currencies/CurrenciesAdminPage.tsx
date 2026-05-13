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
import { useCurrencies, useDeleteCurrency } from "./hooks";
import { currencyColumns } from "./columns";
import { CurrencyFormDialog } from "./components/CurrencyFormDialog";
import type { Currency } from "./schemas";

const PAGE_SIZE = 50;

interface CurrencyFiltersState {
  search?: string;
  page?: number;
}

function paramsToFilters(params: URLSearchParams): CurrencyFiltersState {
  const page = Number(params.get("page") ?? "1");
  return {
    search: params.get("q") ?? undefined,
    page: Number.isFinite(page) && page > 0 ? page : 1,
  };
}

export function CurrenciesAdminPage() {
  const { t } = useTranslation("admin");
  const [params, setParams] = useSearchParams();
  const filters = useMemo(() => paramsToFilters(params), [params.toString()]); // eslint-disable-line react-hooks/exhaustive-deps
  const [search, setSearch] = useState(filters.search ?? "");
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<Currency | null>(null);
  const [deleting, setDeleting] = useState<Currency | null>(null);
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

  const query = useCurrencies(filters);
  const pageCount = query.data ? Math.max(1, Math.ceil(query.data.count / PAGE_SIZE)) : 1;
  const columns = useMemo(() => currencyColumns(t), [t]);

  return (
    <AdminPageShell
      title={t("currencies.title")}
      description={t("currencies.description")}
      actions={
        <Button size="sm" onClick={() => setCreateOpen(true)} disabled={!canWrite}>
          {t("currencies.new_button")}
        </Button>
      }
    >
      <Toolbar
        searchValue={search}
        onSearchChange={setSearch}
        searchPlaceholder={t("currencies.filters.search_placeholder")}
      />

      {query.isError ? (
        <ErrorState
          description={t("currencies.errors.load_failed")}
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
                  onEdit={() => setEditing(row.original)}
                  onDelete={() => setDeleting(row.original)}
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
          rowKey={(row) => row.code}
          emptyContent={
            <EmptyState
              title={t("currencies.empty.title")}
              description={t("currencies.empty.description")}
            />
          }
        />
      )}

      {createOpen ? (
        <CurrencyFormDialog mode="create" open={createOpen} onOpenChange={setCreateOpen} />
      ) : null}
      {editing ? (
        <CurrencyFormDialog
          mode="edit"
          currency={editing}
          open={editing != null}
          onOpenChange={(o) => {
            if (!o) setEditing(null);
          }}
        />
      ) : null}
      {deleting ? (
        <DeleteCurrencyConfirm currency={deleting} onClose={() => setDeleting(null)} />
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

function DeleteCurrencyConfirm({ currency, onClose }: { currency: Currency; onClose: () => void }) {
  const { t } = useTranslation("admin");
  const mutation = useDeleteCurrency(currency.code);
  const onConfirm = async () => {
    try {
      await mutation.mutateAsync();
      toast.success(t("currencies.toasts.deleted"));
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
      title={t("currencies.confirm_delete.title")}
      description={t("currencies.confirm_delete.description")}
      confirmLabel={t("currencies.confirm_delete.confirm")}
      busy={mutation.isPending}
      destructive
    />
  );
}
