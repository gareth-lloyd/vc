import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { ChevronLeft } from "lucide-react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Section } from "@/components/data/Section";
import { FactList, FactRow } from "@/components/data/FactList";
import { StatusBadge } from "@/components/data/StatusBadge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { ApiError } from "@/lib/api/errors";
import { formatDate } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/money";
import { BookingApprovalActions } from "./BookingApprovalActions";
import { useOwnerBooking } from "./hooks";
import type { OwnerPaymentSplit } from "./schemas";

// GAP-077 — one card per scheduled component (deposit / balance) with the
// owner-money breakdown. Lean owner-portal rendering of the staff FinanceTab
// split table (bookings is off-limits per the GAP-063 boundary).
function PaymentSplitCard({
  split,
  currency,
}: {
  split: OwnerPaymentSplit;
  currency: string | null;
}) {
  const { t } = useTranslation("owner");
  const label =
    split.purpose === "deposit"
      ? t("booking_detail.payment_schedule.deposit")
      : t("booking_detail.payment_schedule.balance");

  return (
    <div
      className="bg-card shadow-card rounded-lg border"
      data-testid={`payment-split-${split.purpose}`}
    >
      <div className="border-border flex items-baseline justify-between gap-4 border-b px-4 py-2 text-sm">
        <span className="font-medium">
          {label}
          {split.status === "waived" ? (
            <span className="text-muted-foreground ml-2 text-xs font-normal italic">
              {t("booking_detail.payment_schedule.waived")}
            </span>
          ) : null}
        </span>
        {split.due_at ? (
          <span className="text-muted-foreground text-xs">
            {/* due_at is stored midnight-UTC; render the UTC day, not the
                viewer's local one (west-of-UTC would show the day before). */}
            {t("booking_detail.payment_schedule.due", {
              date: formatDate(split.due_at.slice(0, 10)),
            })}
          </span>
        ) : null}
      </div>
      <FactList>
        <FactRow
          label={t("booking_detail.payment_schedule.gross")}
          value={formatMoney(split.gross, currency)}
        />
        <FactRow
          label={t("booking_detail.payment_schedule.commission")}
          value={formatMoney(split.commission, currency)}
        />
        <FactRow
          label={t("booking_detail.payment_schedule.tax")}
          value={formatMoney(split.tax, currency)}
        />
        <FactRow
          label={t("booking_detail.net_to_owner")}
          value={formatMoney(split.net_to_owner, currency)}
        />
      </FactList>
    </div>
  );
}

export function OwnerBookingDetailPage() {
  const { t } = useTranslation("owner");
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const bookingId = id ? Number(id) : undefined;
  const query = useOwnerBooking(bookingId);

  if (query.isLoading) {
    return (
      <div className="space-y-4 p-6">
        <Skeleton className="h-10 w-1/3" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (query.isError) {
    const notFound = query.error instanceof ApiError && query.error.status === 404;
    return (
      <div className="p-6">
        <ErrorState
          title={notFound ? t("booking_detail.not_found_title") : undefined}
          description={
            notFound ? t("booking_detail.not_found_body") : t("booking_detail.load_failed")
          }
          onRetry={notFound ? undefined : () => query.refetch()}
        />
      </div>
    );
  }

  const booking = query.data;
  if (!booking) return null;

  const currency = booking.currency_code;
  const awaitingApproval = booking.status === "pending_owner_approval" && booking.can_approve;

  return (
    <div>
      <PageHeader
        title={booking.reference}
        breadcrumbs={[
          { label: t("nav.bookings"), to: "/owner/bookings" },
          { label: booking.reference },
        ]}
        actions={
          <div className="flex items-center gap-2">
            {awaitingApproval ? <BookingApprovalActions bookingId={booking.id} /> : null}
            <Button variant="outline" size="sm" onClick={() => navigate("/owner/bookings")}>
              <ChevronLeft className="mr-1 size-4" /> {t("booking_detail.back")}
            </Button>
          </div>
        }
      />
      <div className="grid grid-cols-1 gap-8 px-6 pb-12 lg:grid-cols-2">
        <Section title={t("booking_detail.stay")}>
          <div className="bg-card shadow-card rounded-lg border">
            <FactList>
              <FactRow label={t("booking_detail.property")} value={booking.property_name ?? "—"} />
              <FactRow
                label={t("booking_detail.dates")}
                value={`${formatDate(booking.date_from)} – ${formatDate(booking.date_to)}`}
              />
              <FactRow
                label={t("booking_detail.party")}
                value={t("bookings.party", {
                  adults: booking.adults,
                  children: booking.children,
                })}
              />
              <FactRow
                label={t("booking_detail.status")}
                value={<StatusBadge status={booking.status} />}
              />
            </FactList>
          </div>
        </Section>

        <Section title={t("booking_detail.guest")}>
          <div className="bg-card shadow-card rounded-lg border">
            <FactList>
              <FactRow label={t("booking_detail.guest_name")} value={booking.guest_name ?? "—"} />
              <FactRow
                label={t("booking_detail.guest_country")}
                value={booking.guest_country?.name ?? "—"}
              />
              <FactRow
                label={t("booking_detail.repeat_guest")}
                value={
                  booking.is_repeat_guest
                    ? t("booking_detail.repeat_yes")
                    : t("booking_detail.repeat_no")
                }
              />
              <FactRow
                label={t("booking_detail.contact")}
                value={
                  booking.guest_contact ? (
                    <div className="space-y-0.5">
                      <div>{booking.guest_contact.email}</div>
                      <div className="text-muted-foreground">{booking.guest_contact.phone}</div>
                    </div>
                  ) : (
                    <span className="text-muted-foreground">
                      {t("booking_detail.contact_via_vc")}
                    </span>
                  )
                }
              />
            </FactList>
          </div>
        </Section>

        {booking.gross_total != null ? (
          <Section title={t("booking_detail.money")}>
            <div className="bg-card shadow-card rounded-lg border">
              <FactList>
                <FactRow
                  label={t("booking_detail.gross_total")}
                  value={formatMoney(booking.gross_total, currency)}
                />
                {booking.commission != null ? (
                  <FactRow
                    label={t("booking_detail.commission")}
                    value={formatMoney(booking.commission, currency)}
                  />
                ) : null}
                {booking.net_to_owner != null ? (
                  <FactRow
                    label={t("booking_detail.net_to_owner")}
                    value={formatMoney(booking.net_to_owner, currency)}
                  />
                ) : null}
              </FactList>
            </div>
          </Section>
        ) : null}

        {/* GAP-077: per-component owner-money split of the payment schedule.
            Absent (not empty-stated) without the view_full_money grant or
            when there is no schedule to split. */}
        {(() => {
          // Unknown future purposes (e.g. a planned INTERIM instalment) are
          // dropped rather than mislabelled — the schema stays loose so an
          // additive backend change can never kill the whole page.
          const splits = (booking.payment_splits ?? []).filter(
            (s) => s.purpose === "deposit" || s.purpose === "balance",
          );
          return splits.length > 0 ? (
            <Section title={t("booking_detail.payment_schedule.title")}>
              <div className="space-y-4">
                {splits.map((split) => (
                  <PaymentSplitCard key={split.purpose} split={split} currency={currency} />
                ))}
              </div>
            </Section>
          ) : null;
        })()}
      </div>
    </div>
  );
}
