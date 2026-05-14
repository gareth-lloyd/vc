import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useOutletContext } from "react-router-dom";
import { toast } from "sonner";
import type { ColumnDef, SortingState } from "@tanstack/react-table";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { DataTable } from "@/components/data/DataTable";
import { StatusBadge } from "@/components/data/StatusBadge";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { ApiError } from "@/lib/api/errors";
import { formatMoney, parseMoney } from "@/lib/format/money";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import {
  useBookingConciergeItems,
  useConfirmConciergeItem,
  useDeleteConciergeItem,
} from "../hooks";
import { ConciergeItemFormDialog } from "../components/ConciergeItemFormDialog";
import {
  conciergeStatusLabel,
  conciergeTierLabel,
  conciergeUnitLabel,
  type BookingConciergeItem,
} from "../schemas";
import type { BookingOutletContext } from "../BookingDetailLayout";

function lineTotal(item: BookingConciergeItem): number {
  const price = parseMoney(item.unit_price);
  if (!Number.isFinite(price)) return Number.NaN;
  return price * item.quantity;
}

export function ConciergeTab() {
  const { t } = useTranslation("bookings");
  const { booking } = useOutletContext<BookingOutletContext>();
  const canWrite = useHasReservationsRole();
  const currency = booking.currency_code ?? null;

  const items = useBookingConciergeItems(booking.id);
  const confirmMutation = useConfirmConciergeItem(booking.id);
  const deleteMutation = useDeleteConciergeItem(booking.id);

  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<BookingConciergeItem | null>(null);
  const [deleting, setDeleting] = useState<BookingConciergeItem | null>(null);
  const [sorting, setSorting] = useState<SortingState>([]);

  const rows = items.data?.results ?? [];

  const handleConfirm = async (item: BookingConciergeItem) => {
    try {
      await confirmMutation.mutateAsync({ itemId: item.id });
      toast.success(t("concierge.toasts.confirmed"));
    } catch (error) {
      const message =
        error instanceof ApiError ? error.detail : t("concierge.toasts.confirm_failed");
      toast.error(message);
    }
  };

  const handleDelete = async () => {
    if (!deleting) return;
    try {
      await deleteMutation.mutateAsync({ itemId: deleting.id });
      toast.success(t("concierge.toasts.removed"));
      setDeleting(null);
    } catch {
      toast.error(t("concierge.toasts.remove_failed"));
    }
  };

  const columns: ColumnDef<BookingConciergeItem>[] = useMemo(
    () => [
      {
        accessorKey: "name",
        header: t("concierge.columns.service"),
        cell: ({ row }) => (
          <div className="space-y-0.5">
            <div className="font-medium">{row.original.name}</div>
            <div className="text-muted-foreground text-xs">
              {conciergeTierLabel(row.original.tier)}
            </div>
          </div>
        ),
      },
      {
        accessorKey: "description",
        header: t("concierge.columns.description"),
        cell: ({ row }) => (
          <span className="text-muted-foreground line-clamp-2 text-sm">
            {row.original.description || "—"}
          </span>
        ),
      },
      {
        accessorKey: "quantity",
        header: t("concierge.columns.qty"),
        cell: ({ row }) =>
          t("concierge.row.qty_with_unit", {
            quantity: row.original.quantity,
            unit: conciergeUnitLabel(row.original.unit),
          }),
      },
      {
        accessorKey: "unit_price",
        header: t("concierge.columns.unit_price"),
        cell: ({ row }) => formatMoney(row.original.unit_price, currency),
      },
      {
        id: "total",
        header: t("concierge.columns.total"),
        cell: ({ row }) => formatMoney(lineTotal(row.original), currency),
      },
      {
        accessorKey: "status",
        header: t("concierge.columns.status"),
        cell: ({ row }) => <StatusBadge status={conciergeStatusLabel(row.original.status)} />,
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => {
          if (!canWrite) return null;
          const item = row.original;
          return (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={t("concierge.row.actions_for", { name: item.name })}
                >
                  {t("concierge.row.actions_label")}
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => setEditing(item)}>
                  {t("common:actions.edit")}
                </DropdownMenuItem>
                {item.status === "requested" ? (
                  <DropdownMenuItem onClick={() => handleConfirm(item)}>
                    {t("concierge.menu.confirm")}
                  </DropdownMenuItem>
                ) : null}
                <DropdownMenuItem className="text-destructive" onClick={() => setDeleting(item)}>
                  {t("common:actions.delete")}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          );
        },
      },
    ],
    // handleConfirm/handleCancel close over mutations, but they're stable enough
    // for our use; rebuild on relevant inputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [canWrite, currency, t],
  );

  if (items.isLoading) {
    return (
      <div className="space-y-4 p-6">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (items.isError) {
    return (
      <div className="p-6">
        <ErrorState
          title={t("concierge.load_failed_title")}
          description={t("concierge.load_failed_body")}
          onRetry={() => items.refetch()}
        />
      </div>
    );
  }

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-foreground text-lg font-semibold">{t("concierge.heading")}</h2>
        {canWrite ? (
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            {t("concierge.add_service")}
          </Button>
        ) : (
          <Tooltip>
            <TooltipTrigger asChild>
              <span>
                <Button size="sm" disabled>
                  {t("concierge.add_service")}
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent>{t("concierge.role_required_tooltip")}</TooltipContent>
          </Tooltip>
        )}
      </div>

      <DataTable
        columns={columns}
        data={rows}
        pageIndex={0}
        pageCount={1}
        sorting={sorting}
        onSortingChange={setSorting}
        onPageChange={() => {}}
        rowKey={(row) => row.id}
        emptyContent={<EmptyState title={t("concierge.empty_title")} />}
      />

      {createOpen ? (
        <ConciergeItemFormDialog
          mode="create"
          bookingId={booking.id}
          defaultCurrency={booking.currency}
          open={createOpen}
          onOpenChange={setCreateOpen}
        />
      ) : null}

      {editing ? (
        <ConciergeItemFormDialog
          mode="edit"
          bookingId={booking.id}
          defaultCurrency={booking.currency}
          item={editing}
          open
          onOpenChange={(open) => {
            if (!open) setEditing(null);
          }}
        />
      ) : null}

      {deleting ? (
        <ConfirmDialog
          open
          onOpenChange={(open) => {
            if (!open) setDeleting(null);
          }}
          onConfirm={handleDelete}
          title={t("concierge.confirm_delete.title")}
          description={t("concierge.confirm_delete.description")}
          confirmLabel={t("concierge.confirm_delete.confirm_label")}
          destructive
          busy={deleteMutation.isPending}
        />
      ) : null}
    </div>
  );
}
