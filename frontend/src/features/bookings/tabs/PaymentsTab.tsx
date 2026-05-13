import { useOutletContext } from "react-router-dom";
import { Section } from "@/components/data/Section";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { useBalanceTrack, useDepositTrack, useSecurityTrack } from "../hooks";
import { PaymentTrack } from "../components/PaymentTrack";
import { TransactionsTable } from "../components/TransactionsTable";
import type { BookingOutletContext } from "../BookingDetailLayout";

export function PaymentsTab() {
  const { booking } = useOutletContext<BookingOutletContext>();
  const canWrite = useHasReservationsRole();
  const currency = booking.currency_code ?? null;

  const deposit = useDepositTrack(booking.id);
  const balance = useBalanceTrack(booking.id);
  const security = useSecurityTrack(booking.id);

  return (
    <div className="space-y-6 p-6">
      <h2 className="text-foreground text-lg font-semibold">Payments</h2>

      <div className="space-y-3">
        <PaymentTrack
          bookingId={booking.id}
          trackName="deposit"
          trackLabel="Deposit"
          data={deposit.data}
          isLoading={deposit.isLoading}
          isError={deposit.isError}
          onRetry={() => deposit.refetch()}
          currency={currency}
          canWrite={canWrite}
        />
        <PaymentTrack
          bookingId={booking.id}
          trackName="balance"
          trackLabel="Balance"
          data={balance.data}
          isLoading={balance.isLoading}
          isError={balance.isError}
          onRetry={() => balance.refetch()}
          currency={currency}
          canWrite={canWrite}
        />
        <PaymentTrack
          bookingId={booking.id}
          trackName="security"
          trackLabel="Security deposit"
          data={security.data}
          isLoading={security.isLoading}
          isError={security.isError}
          onRetry={() => security.refetch()}
          currency={currency}
          canWrite={canWrite}
        />
      </div>

      <Section title="Transactions">
        <TransactionsTable bookingId={booking.id} currency={currency} />
      </Section>
    </div>
  );
}
