import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ColumnDef, SortingState } from "@tanstack/react-table";
import { useQuery } from "@tanstack/react-query";
import { DataTable } from "@/components/data/DataTable";
import { StatusBadge } from "@/components/data/StatusBadge";
import { EmptyState } from "@/components/feedback/EmptyState";
import { queryKeys, type BookingId } from "@/lib/query/keys";
import { formatDate } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/money";
import { fetchTrackPayments } from "../api";
import { paymentTrackStatusLabel, type PaymentRecord, type PaymentTrackStatus } from "../schemas";

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
  const { t } = useTranslation("bookings");
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
      ...(deposit.data ?? []).map((r) => ({ ...r, trackLabel: t("payments.tracks.deposit") })),
      ...(balance.data ?? []).map((r) => ({ ...r, trackLabel: t("payments.tracks.balance") })),
      ...(security.data ?? []).map((r) => ({
        ...r,
        trackLabel: t("payments.tracks.security_short"),
      })),
    ];
    merged.sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""));
    return merged;
  }, [deposit.data, balance.data, security.data, t]);

  const columns: ColumnDef<TransactionRow>[] = useMemo(
    () => [
      {
        accessorKey: "created_at",
        header: t("payments.transactions.headers.date"),
        cell: ({ row }) => (row.original.created_at ? formatDate(row.original.created_at) : "—"),
      },
      { accessorKey: "trackLabel", header: t("payments.transactions.headers.track") },
      {
        accessorKey: "amount",
        header: t("payments.transactions.headers.amount"),
        cell: ({ row }) => formatMoney(row.original.amount, currency),
      },
      {
        accessorKey: "status",
        header: t("payments.transactions.headers.status"),
        cell: ({ row }) => (
          <StatusBadge
            status={
              paymentTrackStatusLabel(row.original.status as PaymentTrackStatus) ??
              row.original.status
            }
          />
        ),
      },
      {
        accessorKey: "payment_method",
        header: t("payments.transactions.headers.method"),
        cell: ({ row }) => row.original.payment_method || "—",
      },
      {
        accessorKey: "provider_reference",
        header: t("payments.transactions.headers.reference"),
        cell: ({ row }) => row.original.provider_reference || "—",
      },
    ],
    [currency, t],
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
      emptyContent={<EmptyState title={t("payments.transactions.empty")} />}
    />
  );
}
