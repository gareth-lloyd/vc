import { useOutletContext } from "react-router-dom";
import { Section } from "@/components/data/Section";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { useBalanceTrack, useDepositTrack, useSecurityTrack } from "../hooks";
import { PaymentTrack } from "../components/PaymentTrack";
import { TransactionsTable } from "../components/TransactionsTable";
import type { TrackName } from "../api";
import type { BookingOutletContext } from "../BookingDetailLayout";

const TRACKS: { name: TrackName; label: string }[] = [
  { name: "deposit", label: "Deposit" },
  { name: "balance", label: "Balance" },
  { name: "security", label: "Security deposit" },
];

export function PaymentsTab() {
  const { booking } = useOutletContext<BookingOutletContext>();
  const canWrite = useHasReservationsRole();
  const currency = booking.currency_code ?? null;

  const queries = {
    deposit: useDepositTrack(booking.id),
    balance: useBalanceTrack(booking.id),
    security: useSecurityTrack(booking.id),
  };

  return (
    <div className="space-y-6 p-6">
      <h2 className="text-foreground text-lg font-semibold">Payments</h2>

      <div className="space-y-3">
        {TRACKS.map(({ name, label }) => {
          const q = queries[name];
          return (
            <PaymentTrack
              key={name}
              bookingId={booking.id}
              trackName={name}
              trackLabel={label}
              data={q.data}
              isLoading={q.isLoading}
              isError={q.isError}
              onRetry={() => q.refetch()}
              currency={currency}
              canWrite={canWrite}
            />
          );
        })}
      </div>

      <Section title="Transactions">
        <TransactionsTable bookingId={booking.id} currency={currency} />
      </Section>
    </div>
  );
}
