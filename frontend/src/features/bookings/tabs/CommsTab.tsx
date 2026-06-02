import { useState } from "react";
import { ActivityList } from "@/components/data/ActivityList";
import { useTranslation } from "react-i18next";
import { useOutletContext } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/data/StatusBadge";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { ApiError } from "@/lib/api/errors";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { formatDate } from "@/lib/format/date";
import { useBookingEmails, useResendBookingEmail } from "../hooks";
import { emailLogStatusLabel, type BookingEmail, type EmailLogStatus } from "../schemas";
import type { BookingOutletContext } from "../BookingDetailLayout";

const STATUS_KIND: Record<EmailLogStatus, "active" | "pending" | "error"> = {
  sent: "active",
  queued: "pending",
  failed: "error",
  bounced: "error",
};

function summariseRecipients(emails: BookingEmail) {
  const [first, ...rest] = emails.to;
  if (!first) return "—";
  if (rest.length === 0) return first;
  return `${first} +${rest.length}`;
}

function generateIdempotencyKey(): string {
  // Use crypto.randomUUID when available; fall back to a timestamp-based id
  // for older browsers (the call is for protecting against a double-click,
  // not a security boundary).
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `resend-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function CommsTab() {
  const { t } = useTranslation("bookings");
  const { booking } = useOutletContext<BookingOutletContext>();
  const canWrite = useHasReservationsRole();
  const emails = useBookingEmails(booking.id);
  const resend = useResendBookingEmail(booking.id);
  const [pendingResend, setPendingResend] = useState<BookingEmail | null>(null);

  if (emails.isLoading) {
    return (
      <div className="p-6">
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (emails.isError) {
    return (
      <div className="p-6">
        <ErrorState
          title={t("comms.load_failed_title")}
          description={t("comms.load_failed_body")}
          onRetry={() => emails.refetch()}
        />
      </div>
    );
  }

  const rows = emails.data?.results ?? [];
  if (rows.length === 0) {
    return (
      <div className="p-6">
        <EmptyState title={t("comms.empty_title")} description={t("comms.empty_body")} />
      </div>
    );
  }

  const handleConfirmResend = async () => {
    if (!pendingResend) return;
    try {
      await resend.mutateAsync({
        emailId: pendingResend.id,
        idempotencyKey: generateIdempotencyKey(),
      });
      toast.success(t("comms.resend.toast_success"));
    } catch (error) {
      const message =
        error instanceof ApiError && error.isClientError()
          ? error.detail
          : t("comms.resend.toast_failed");
      toast.error(message);
    } finally {
      setPendingResend(null);
    }
  };

  return (
    <div className="p-6">
      <ActivityList as="ol">
        {rows.map((email) => {
          const timestamp = email.sent_at ?? email.queued_at ?? null;
          return (
            <li key={email.id} className="px-4 py-3 text-sm">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1 space-y-1">
                  <p className="text-foreground font-medium break-words">{email.subject || "—"}</p>
                  <p className="text-muted-foreground text-xs">
                    {t("comms.fields.to")}: {summariseRecipients(email)}
                  </p>
                  <p className="text-muted-foreground text-xs">
                    {t("comms.fields.template")}: {email.template_key} · v{email.template_version}
                  </p>
                  {email.failure_reason ? (
                    <p className="text-danger text-xs">{email.failure_reason}</p>
                  ) : null}
                </div>
                <div className="flex flex-col items-end gap-2">
                  <StatusBadge
                    status={emailLogStatusLabel(email.status)}
                    kind={STATUS_KIND[email.status]}
                  />
                  <span className="text-muted-foreground text-xs">{formatDate(timestamp)}</span>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => setPendingResend(email)}
                    disabled={
                      !canWrite || (resend.isPending && resend.variables?.emailId === email.id)
                    }
                  >
                    {t("comms.resend.action")}
                  </Button>
                </div>
              </div>
            </li>
          );
        })}
      </ActivityList>

      <ConfirmDialog
        open={pendingResend != null}
        onOpenChange={(open) => !open && setPendingResend(null)}
        onConfirm={handleConfirmResend}
        title={t("comms.resend.confirm_title")}
        description={t("comms.resend.confirm_body", {
          subject: pendingResend?.subject ?? "",
          to: pendingResend ? summariseRecipients(pendingResend) : "",
        })}
        confirmLabel={t("comms.resend.confirm_button")}
        busy={resend.isPending}
      />
    </div>
  );
}
