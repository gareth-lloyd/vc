import { useMemo, useState } from "react";
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
  CONCIERGE_STATUS_LABELS,
  CONCIERGE_TIER_LABELS,
  CONCIERGE_UNIT_LABELS,
  type BookingConciergeItem,
} from "../schemas";
import type { BookingOutletContext } from "../BookingDetailLayout";

function lineTotal(item: BookingConciergeItem): number {
  const price = parseMoney(item.unit_price);
  if (!Number.isFinite(price)) return Number.NaN;
  return price * item.quantity;
}

export function ConciergeTab() {
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
      toast.success("Service confirmed");
    } catch (error) {
      const message = error instanceof ApiError ? error.detail : "Couldn't confirm";
      toast.error(message);
    }
  };

  const handleDelete = async () => {
    if (!deleting) return;
    try {
      await deleteMutation.mutateAsync({ itemId: deleting.id });
      toast.success("Service removed");
      setDeleting(null);
    } catch {
      toast.error("Couldn't remove service");
    }
  };

  const columns: ColumnDef<BookingConciergeItem>[] = useMemo(
    () => [
      {
        accessorKey: "name",
        header: "Service",
        cell: ({ row }) => (
          <div className="space-y-0.5">
            <div className="font-medium">{row.original.name}</div>
            <div className="text-muted-foreground text-xs">
              {CONCIERGE_TIER_LABELS[row.original.tier]}
            </div>
          </div>
        ),
      },
      {
        accessorKey: "description",
        header: "Description",
        cell: ({ row }) => (
          <span className="text-muted-foreground line-clamp-2 text-sm">
            {row.original.description || "—"}
          </span>
        ),
      },
      {
        accessorKey: "quantity",
        header: "Qty",
        cell: ({ row }) => `${row.original.quantity} ${CONCIERGE_UNIT_LABELS[row.original.unit]}`,
      },
      {
        accessorKey: "unit_price",
        header: "Unit price",
        cell: ({ row }) => formatMoney(row.original.unit_price, currency),
      },
      {
        id: "total",
        header: "Total",
        cell: ({ row }) => formatMoney(lineTotal(row.original), currency),
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => <StatusBadge status={CONCIERGE_STATUS_LABELS[row.original.status]} />,
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
                <Button variant="ghost" size="sm" aria-label={`Actions for ${item.name}`}>
                  Actions
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => setEditing(item)}>Edit</DropdownMenuItem>
                {item.status === "requested" ? (
                  <DropdownMenuItem onClick={() => handleConfirm(item)}>Confirm</DropdownMenuItem>
                ) : null}
                <DropdownMenuItem className="text-destructive" onClick={() => setDeleting(item)}>
                  Delete
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
    [canWrite, currency],
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
          title="Couldn't load concierge services"
          description="Try again."
          onRetry={() => items.refetch()}
        />
      </div>
    );
  }

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-foreground text-lg font-semibold">Concierge</h2>
        {canWrite ? (
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            Add service
          </Button>
        ) : (
          <Tooltip>
            <TooltipTrigger asChild>
              <span>
                <Button size="sm" disabled>
                  Add service
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent>You need the Reservations role to add services</TooltipContent>
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
        emptyContent={<EmptyState title="No concierge services yet" />}
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
          title="Remove this service?"
          description="This can't be undone."
          confirmLabel="Remove"
          destructive
          busy={deleteMutation.isPending}
        />
      ) : null}
    </div>
  );
}
