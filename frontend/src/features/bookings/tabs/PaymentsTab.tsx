import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useOutletContext } from "react-router-dom";
import { Section } from "@/components/data/Section";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { useBalanceTrack, useDepositTrack, useSecurityTrack } from "../hooks";
import { PaymentTrack } from "../components/PaymentTrack";
import { TransactionsTable } from "../components/TransactionsTable";
import type { TrackName } from "../api";
import type { BookingOutletContext } from "../BookingDetailLayout";

export function PaymentsTab() {
  const { t } = useTranslation("bookings");
  const { booking } = useOutletContext<BookingOutletContext>();
  const canWrite = useHasReservationsRole();
  const currency = booking.currency_code ?? null;

  const tracks: { name: TrackName; label: string }[] = useMemo(
    () => [
      { name: "deposit", label: t("payments.tracks.deposit") },
      { name: "balance", label: t("payments.tracks.balance") },
      { name: "security", label: t("payments.tracks.security") },
    ],
    [t],
  );

  const queries = {
    deposit: useDepositTrack(booking.id),
    balance: useBalanceTrack(booking.id),
    security: useSecurityTrack(booking.id),
  };

  return (
    <div className="space-y-6 p-6">
      <h2 className="text-foreground text-lg font-semibold">{t("payments.heading")}</h2>

      <div className="space-y-3">
        {tracks.map(({ name, label }) => {
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

      <Section title={t("payments.transactions_heading")}>
        <TransactionsTable bookingId={booking.id} currency={currency} />
      </Section>
    </div>
  );
}
