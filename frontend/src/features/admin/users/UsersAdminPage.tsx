import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import type { SortingState } from "@tanstack/react-table";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { orderingToSorting, sortingToOrdering } from "@/lib/drf/sorting";
import { useHasAdminRole } from "@/lib/auth/useHasAdminRole";
import { useActivateUser, useDeactivateUser, useReset2fa, useUsers } from "@/features/users/hooks";
import { STAFF_ROLES, type UserSummary } from "@/features/users/schemas";
import { userColumns } from "./columns";
import { UserFormDialog } from "./components/UserFormDialog";
import { MoreHorizontal } from "lucide-react";

const ALL_VALUE = "__all__";
const PAGE_SIZE = 50;

interface UsersFilters {
  search?: string;
  role?: string;
  is_active?: boolean;
  ordering?: string;
  page?: number;
}

function paramsToFilters(params: URLSearchParams): UsersFilters {
  const page = Number(params.get("page") ?? "1");
  const active = params.get("is_active");
  return {
    search: params.get("q") ?? undefined,
    role: params.get("role") ?? undefined,
    is_active: active == null ? undefined : active === "true",
    ordering: params.get("ordering") ?? undefined,
    page: Number.isFinite(page) && page > 0 ? page : 1,
  };
}

export function UsersAdminPage() {
  const { t } = useTranslation("admin");
  const [params, setParams] = useSearchParams();
  const filters = useMemo(() => paramsToFilters(params), [params.toString()]); // eslint-disable-line react-hooks/exhaustive-deps
  const [search, setSearch] = useState(filters.search ?? "");
  const [createOpen, setCreateOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<UserSummary | null>(null);
  const [resetTfaUser, setResetTfaUser] = useState<UserSummary | null>(null);
  const [toggleActiveUser, setToggleActiveUser] = useState<UserSummary | null>(null);
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

  const query = useUsers(filters);
  const pageCount = query.data ? Math.max(1, Math.ceil(query.data.count / PAGE_SIZE)) : 1;
  const sorting = useMemo(() => orderingToSorting(filters.ordering), [filters.ordering]);

  const columns = useMemo(() => userColumns(t), [t]);

  const newButton = (
    <Button size="sm" onClick={() => setCreateOpen(true)} disabled={!canWrite}>
      {t("users.new_button")}
    </Button>
  );

  return (
    <AdminPageShell
      title={t("users.title")}
      description={t("users.description")}
      actions={newButton}
    >
      <Toolbar
        searchValue={search}
        onSearchChange={setSearch}
        searchPlaceholder={t("users.filters.search_placeholder")}
        filters={
          <div className="flex items-center gap-2">
            <Select value={filters.role ?? ALL_VALUE} onValueChange={(v) => updateParam("role", v)}>
              <SelectTrigger className="w-[160px]" aria-label={t("users.filters.role_label")}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL_VALUE}>{t("users.filters.role_any")}</SelectItem>
                {STAFF_ROLES.map((r) => (
                  <SelectItem key={r} value={r}>
                    {t(`users.roles.${r}` as "users.roles.admin")}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={
                filters.is_active === undefined ? ALL_VALUE : filters.is_active ? "true" : "false"
              }
              onValueChange={(v) => updateParam("is_active", v)}
            >
              <SelectTrigger className="w-[140px]" aria-label={t("users.filters.active_label")}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL_VALUE}>{t("users.filters.active_any")}</SelectItem>
                <SelectItem value="true">{t("users.filters.active_yes")}</SelectItem>
                <SelectItem value="false">{t("users.filters.active_no")}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        }
      />

      {query.isError ? (
        <ErrorState
          description={t("users.errors.load_failed")}
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
                  user={row.original}
                  canWrite={canWrite}
                  onEdit={() => setEditingUser(row.original)}
                  onResetTfa={() => setResetTfaUser(row.original)}
                  onToggleActive={() => setToggleActiveUser(row.original)}
                />
              ),
            },
          ]}
          data={query.data?.results}
          isLoading={query.isLoading}
          pageIndex={(filters.page ?? 1) - 1}
          pageCount={pageCount}
          pageSize={PAGE_SIZE}
          sorting={sorting}
          onSortingChange={onSortingChange}
          onPageChange={goToPage}
          rowKey={(row) => row.id}
          emptyContent={
            <EmptyState title={t("users.empty.title")} description={t("users.empty.description")} />
          }
        />
      )}

      {createOpen ? (
        <UserFormDialog mode="create" open={createOpen} onOpenChange={setCreateOpen} />
      ) : null}
      {editingUser ? (
        <UserFormDialog
          mode="edit"
          user={editingUser}
          open={editingUser != null}
          onOpenChange={(o) => {
            if (!o) setEditingUser(null);
          }}
        />
      ) : null}
      {resetTfaUser ? (
        <ResetTfaConfirm user={resetTfaUser} onClose={() => setResetTfaUser(null)} />
      ) : null}
      {toggleActiveUser ? (
        <ToggleActiveConfirm user={toggleActiveUser} onClose={() => setToggleActiveUser(null)} />
      ) : null}
    </AdminPageShell>
  );
}

interface RowActionsProps {
  user: UserSummary;
  canWrite: boolean;
  onEdit: () => void;
  onResetTfa: () => void;
  onToggleActive: () => void;
}

function RowActions({ user, canWrite, onEdit, onResetTfa, onToggleActive }: RowActionsProps) {
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
        <DropdownMenuItem onSelect={onEdit}>{t("users.row_actions.edit")}</DropdownMenuItem>
        <DropdownMenuItem onSelect={onResetTfa}>
          {t("users.row_actions.reset_2fa")}
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={onToggleActive}>
          {user.is_active ? t("users.row_actions.deactivate") : t("users.row_actions.activate")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function ResetTfaConfirm({ user, onClose }: { user: UserSummary; onClose: () => void }) {
  const { t } = useTranslation("admin");
  const mutation = useReset2fa(user.id);
  const onConfirm = async () => {
    try {
      await mutation.mutateAsync();
      toast.success(t("users.toasts.reset_2fa"));
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
      title={t("users.confirm_reset_2fa.title")}
      description={t("users.confirm_reset_2fa.description")}
      confirmLabel={t("users.confirm_reset_2fa.confirm")}
      busy={mutation.isPending}
      destructive
    />
  );
}

function ToggleActiveConfirm({ user, onClose }: { user: UserSummary; onClose: () => void }) {
  const { t } = useTranslation("admin");
  const deactivate = useDeactivateUser(user.id);
  const activate = useActivateUser(user.id);
  const isActive = user.is_active;
  const onConfirm = async () => {
    try {
      if (isActive) {
        await deactivate.mutateAsync();
        toast.success(t("users.toasts.deactivated"));
      } else {
        await activate.mutateAsync();
        toast.success(t("users.toasts.activated"));
      }
      onClose();
    } catch {
      toast.error(t("common:errors.generic"));
    }
  };
  const busy = deactivate.isPending || activate.isPending;
  return (
    <ConfirmDialog
      open
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
      onConfirm={onConfirm}
      title={isActive ? t("users.confirm_deactivate.title") : t("users.confirm_activate.title")}
      description={
        isActive
          ? t("users.confirm_deactivate.description")
          : t("users.confirm_activate.description")
      }
      confirmLabel={
        isActive ? t("users.confirm_deactivate.confirm") : t("users.confirm_activate.confirm")
      }
      busy={busy}
      destructive={isActive}
    />
  );
}
