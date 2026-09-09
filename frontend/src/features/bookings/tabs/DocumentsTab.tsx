import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useOutletContext } from "react-router-dom";
import { toast } from "sonner";
import { ActivityList } from "@/components/data/ActivityList";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { ApiError } from "@/lib/api/errors";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { formatDate } from "@/lib/format/date";
import { downloadBookingDocument } from "../api";
import { ContractPreviewDialog } from "../components/ContractPreviewDialog";
import {
  useBookingDocuments,
  useDeleteBookingDocument,
  useGenerateBookingDocument,
  useSendBookingDocument,
} from "../hooks";
import { bookingDocumentKindLabel, type BookingDocument } from "../schemas";
import type { BookingOutletContext } from "../BookingDetailLayout";

/**
 * Hand the browser a URL it owns for exactly one click.
 *
 * The document bytes never get a URL of their own — the `documents` storage
 * alias is private precisely because a contract carries guest PII — so the
 * download arrives as a blob through the API and has to be saved from memory.
 */
function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  // Revoked on the next task, not this one: Firefox and Safari can tear the
  // blob entry down before the download has started reading it, and a save
  // that dies that way is silent — nothing rejects, so no toast fires.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

function errorMessage(error: unknown, fallback: string): string {
  // A 4xx from these routes always names its cause (`no_recipient`,
  // `document_file_missing`, `document_send_failed`) and the operator can act
  // on it; a 5xx detail is noise, so show ours.
  return error instanceof ApiError && error.isClientError() ? error.detail : fallback;
}

export function DocumentsTab() {
  const { t } = useTranslation("bookings");
  const { booking } = useOutletContext<BookingOutletContext>();
  const canWrite = useHasReservationsRole();
  const documents = useBookingDocuments(booking.id);
  const generate = useGenerateBookingDocument(booking.id);
  const send = useSendBookingDocument(booking.id);
  const remove = useDeleteBookingDocument(booking.id);

  const [pendingSend, setPendingSend] = useState<BookingDocument | null>(null);
  const [pendingDelete, setPendingDelete] = useState<BookingDocument | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [downloading, setDownloading] = useState<ReadonlySet<number>>(new Set());

  const handleGenerate = async () => {
    try {
      await generate.mutateAsync("contract");
      toast.success(t("documents.toasts.generated"));
    } catch (error) {
      toast.error(errorMessage(error, t("documents.toasts.generate_failed")));
    }
  };

  const handleConfirmSend = async () => {
    if (!pendingSend) return;
    try {
      await send.mutateAsync(pendingSend.id);
      toast.success(t("documents.toasts.sent"));
    } catch (error) {
      toast.error(errorMessage(error, t("documents.toasts.send_failed")));
    } finally {
      setPendingSend(null);
    }
  };

  const handleConfirmDelete = async () => {
    if (!pendingDelete) return;
    try {
      await remove.mutateAsync(pendingDelete.id);
      toast.success(t("documents.toasts.deleted"));
    } catch (error) {
      toast.error(errorMessage(error, t("documents.toasts.delete_failed")));
    } finally {
      setPendingDelete(null);
    }
  };

  const handleDownload = async (row: BookingDocument) => {
    // A set, not a scalar: each row has its own button, and a second download
    // started while the first is still streaming would otherwise re-enable
    // the first row mid-flight and clear its busy state early.
    setDownloading((current) => new Set(current).add(row.id));
    try {
      const { blob, filename } = await downloadBookingDocument(booking.id, row.id);
      // The server's own name for the bytes wins: `Content-Disposition` is
      // authoritative, and the list row's filename is only a fallback.
      saveBlob(blob, filename ?? row.filename);
    } catch (error) {
      toast.error(errorMessage(error, t("documents.toasts.download_failed")));
    } finally {
      setDownloading((current) => {
        const next = new Set(current);
        next.delete(row.id);
        return next;
      });
    }
  };

  const rows = documents.data?.results ?? [];
  // Confirmation auto-generates (and emails) the contract, and that path
  // swallows every failure into a log line nobody watches. A confirmed
  // booking with no contract on file is therefore the one staff-visible
  // sign that it failed — say so instead of the neutral "no documents yet".
  // `has_been_confirmed` comes from the API (status + event trail), so a
  // booking cancelled after confirmation is covered too.
  const confirmed = booking.has_been_confirmed === true;
  const missingContract =
    documents.isSuccess && confirmed && !rows.some((row) => row.kind === "contract");
  // The backend refuses a recipient-less send with a 409 `no_recipient`
  // (anonymised guests, agency bookings with no guest address). Nothing on
  // this screen can fix that, so don't offer the button — and don't render a
  // confirmation that reads "will be emailed to ".
  const recipient = booking.guest_email ?? "";

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-foreground text-base font-semibold">{t("documents.heading")}</h2>
        <div className="flex items-center gap-2">
          {/* Previewing needs no stored document — it renders the booking as
              it stands, which is how an operator checks a contract before
              committing one to the guest's history. */}
          <Button type="button" variant="outline" onClick={() => setPreviewOpen(true)}>
            {t("documents.preview")}
          </Button>
          <Button
            type="button"
            onClick={handleGenerate}
            disabled={!canWrite || !confirmed || generate.isPending}
          >
            {t("documents.generate")}
          </Button>
        </div>
      </div>

      {missingContract ? (
        <div
          role="status"
          className="border-warning/40 bg-warning/10 text-warning space-y-1 rounded-md border px-3 py-2 text-sm"
        >
          <p className="font-medium">{t("documents.missing_contract_title")}</p>
          <p>{t("documents.missing_contract_body")}</p>
        </div>
      ) : null}

      {documents.isLoading ? (
        <Skeleton className="h-32 w-full" />
      ) : documents.isError ? (
        <ErrorState
          title={t("documents.load_failed_title")}
          description={t("documents.load_failed_body")}
          onRetry={() => documents.refetch()}
        />
      ) : rows.length === 0 ? (
        missingContract ? null : (
          <EmptyState title={t("documents.empty_title")} description={t("documents.empty_body")} />
        )
      ) : (
        <ActivityList as="ol">
          {rows.map((row) => {
            // `size: null` is the API's one signal that the stored object
            // couldn't be read. Offering Download and Send on that row only
            // buys the operator a 409 — point them at Generate instead.
            const unreadable = row.size === null;
            return (
              <li key={row.id} className="px-4 py-3 text-sm">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1 space-y-1">
                    <p className="text-foreground font-medium break-words">
                      {bookingDocumentKindLabel(row.kind)}
                    </p>
                    <p className="text-muted-foreground text-xs break-all">{row.filename}</p>
                    <p className="text-muted-foreground text-xs">
                      {row.generated_by
                        ? t("documents.generated_by", {
                            date: formatDate(row.generated_at),
                            name: row.generated_by.name,
                          })
                        : t("documents.generated_by_system", {
                            date: formatDate(row.generated_at),
                          })}
                    </p>
                    {unreadable ? (
                      <p className="text-danger text-xs">{t("documents.file_missing")}</p>
                    ) : null}
                    {!recipient ? (
                      <p className="text-muted-foreground text-xs">{t("documents.no_recipient")}</p>
                    ) : null}
                    {row.sent_to_guest_at != null && canWrite ? (
                      <p className="text-muted-foreground text-xs">
                        {t("documents.sent_cannot_delete")}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex flex-col items-end gap-2">
                    <span className="text-muted-foreground text-xs">
                      {row.sent_to_guest_at
                        ? t("documents.sent_at", { date: formatDate(row.sent_to_guest_at) })
                        : t("documents.not_sent")}
                    </span>
                    <div className="flex items-center gap-1">
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() => handleDownload(row)}
                        disabled={unreadable || downloading.has(row.id)}
                      >
                        {t("documents.download")}
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() => setPendingSend(row)}
                        disabled={
                          !canWrite ||
                          unreadable ||
                          !recipient ||
                          (send.isPending && send.variables === row.id)
                        }
                      >
                        {t("documents.send")}
                      </Button>
                      {/* Disabled, not hidden, once sent: the EmailLog that
                          carried it references the blob, so the backend
                          refuses (409). The reason is inline text above,
                          like file_missing / no_recipient — a `title` on a
                          disabled button never shows to keyboard or touch. */}
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() => setPendingDelete(row)}
                        disabled={
                          !canWrite ||
                          row.sent_to_guest_at != null ||
                          (remove.isPending && remove.variables === row.id)
                        }
                      >
                        {t("documents.delete")}
                      </Button>
                    </div>
                  </div>
                </div>
              </li>
            );
          })}
        </ActivityList>
      )}

      {previewOpen ? (
        <ContractPreviewDialog bookingId={booking.id} open onOpenChange={setPreviewOpen} />
      ) : null}

      <ConfirmDialog
        open={pendingSend != null}
        onOpenChange={(open) => !open && setPendingSend(null)}
        onConfirm={handleConfirmSend}
        title={t("documents.confirm_send.title")}
        description={t("documents.confirm_send.body", {
          filename: pendingSend?.filename ?? "",
          // The address is the one thing an operator can still catch before
          // the mail goes out, so it belongs here rather than in a toast.
          email: recipient,
        })}
        confirmLabel={t("documents.confirm_send.button")}
        busy={send.isPending}
      />

      <ConfirmDialog
        open={pendingDelete != null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        onConfirm={handleConfirmDelete}
        title={t("documents.confirm_delete.title")}
        description={t("documents.confirm_delete.body", {
          filename: pendingDelete?.filename ?? "",
        })}
        confirmLabel={t("documents.confirm_delete.button")}
        destructive
        busy={remove.isPending}
      />
    </div>
  );
}
