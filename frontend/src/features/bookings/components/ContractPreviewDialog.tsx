import { useTranslation } from "react-i18next";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import type { BookingId } from "@/lib/query/keys";
import { useBookingDocumentPreview } from "../hooks";

interface ContractPreviewDialogProps {
  bookingId: BookingId;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * The contract as the guest will receive it, rendered from the same seam the
 * stored PDF is printed from (GAP-094) — so an operator can check the house
 * rules that got snapshotted before spending a Generate on it.
 *
 * `sandbox=""` with no allowances: the HTML carries the property's house
 * rules, which are free text an owner typed. The backend escapes them, and
 * this is the second lock on the same door.
 */
export function ContractPreviewDialog({
  bookingId,
  open,
  onOpenChange,
}: ContractPreviewDialogProps) {
  const { t } = useTranslation("bookings");
  const preview = useBookingDocumentPreview(bookingId, "contract");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{t("documents.preview_dialog.title")}</DialogTitle>
          <DialogDescription>{t("documents.preview_dialog.description")}</DialogDescription>
        </DialogHeader>

        {preview.isLoading ? (
          <Skeleton className="h-96 w-full" />
        ) : preview.isError || !preview.data ? (
          <ErrorState
            description={t("documents.preview_dialog.load_failed")}
            onRetry={() => preview.refetch()}
            retrying={preview.isFetching}
          />
        ) : (
          <iframe
            title={t("documents.preview_dialog.iframe_title")}
            srcDoc={preview.data.html}
            sandbox=""
            className="border-border h-[70vh] w-full rounded-md border bg-white"
          />
        )}
      </DialogContent>
    </Dialog>
  );
}
