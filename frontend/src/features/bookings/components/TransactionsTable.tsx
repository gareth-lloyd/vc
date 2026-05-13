import { useMemo, useState } from "react";
import type { ColumnDef, SortingState } from "@tanstack/react-table";
import { useQuery } from "@tanstack/react-query";
import { DataTable } from "@/components/data/DataTable";
import { StatusBadge } from "@/components/data/StatusBadge";
import { EmptyState } from "@/components/feedback/EmptyState";
import { queryKeys, type BookingId } from "@/lib/query/keys";
import { formatDate } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/money";
import { fetchTrackPayments } from "../api";
import {
  PAYMENT_TRACK_STATUS_LABELS,
  type PaymentRecord,
  type PaymentTrackStatus,
} from "../schemas";

interface TransactionsTableProps {
  bookingId: BookingId;
  currency: string | null;
}

interface TransactionRow extends PaymentRecord {
  trackLabel: string;
}

function trackPaymentsKey(bookingId: BookingId, track: "deposit" | "balance" | "security") {
  return [...queryKeys.bookings.detail(bookingId), track, "payments"] as const;
}

export function TransactionsTable({ bookingId, currency }: TransactionsTableProps) {
  const deposit = useQuery({
    queryKey: trackPaymentsKey(bookingId, "deposit"),
    queryFn: () => fetchTrackPayments(bookingId, "deposit"),
  });
  const balance = useQuery({
    queryKey: trackPaymentsKey(bookingId, "balance"),
    queryFn: () => fetchTrackPayments(bookingId, "balance"),
  });
  const security = useQuery({
    queryKey: trackPaymentsKey(bookingId, "security"),
    queryFn: () => fetchTrackPayments(bookingId, "security"),
  });

  const [sorting, setSorting] = useState<SortingState>([{ id: "created_at", desc: true }]);

  const rows: TransactionRow[] = useMemo(() => {
    const merged = [
      ...(deposit.data ?? []).map((r) => ({ ...r, trackLabel: "Deposit" })),
      ...(balance.data ?? []).map((r) => ({ ...r, trackLabel: "Balance" })),
      ...(security.data ?? []).map((r) => ({ ...r, trackLabel: "Security" })),
    ];
    merged.sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""));
    return merged;
  }, [deposit.data, balance.data, security.data]);

  const columns: ColumnDef<TransactionRow>[] = useMemo(
    () => [
      {
        accessorKey: "created_at",
        header: "Date",
        cell: ({ row }) => (row.original.created_at ? formatDate(row.original.created_at) : "—"),
      },
      { accessorKey: "trackLabel", header: "Track" },
      {
        accessorKey: "amount",
        header: "Amount",
        cell: ({ row }) => formatMoney(row.original.amount, currency),
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => (
          <StatusBadge
            status={
              PAYMENT_TRACK_STATUS_LABELS[row.original.status as PaymentTrackStatus] ??
              row.original.status
            }
          />
        ),
      },
      {
        accessorKey: "payment_method",
        header: "Method",
        cell: ({ row }) => row.original.payment_method || "—",
      },
      {
        accessorKey: "provider_reference",
        header: "Reference",
        cell: ({ row }) => row.original.provider_reference || "—",
      },
    ],
    [currency],
  );

  const isLoading = deposit.isLoading || balance.isLoading || security.isLoading;

  return (
    <DataTable
      columns={columns}
      data={rows}
      isLoading={isLoading}
      pageIndex={0}
      pageCount={1}
      sorting={sorting}
      onSortingChange={setSorting}
      onPageChange={() => {}}
      rowKey={(row) => `${row.purpose}-${row.id}`}
      emptyContent={<EmptyState title="No transactions yet" />}
    />
  );
}
