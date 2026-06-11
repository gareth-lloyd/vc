import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/PageHeader";
import { TwoColumn } from "@/components/layout/TwoColumn";
import { StatusBadge } from "@/components/data/StatusBadge";
import { FactList, FactRow } from "@/components/data/FactList";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { ErrorState } from "@/components/feedback/ErrorState";
import { EmptyState } from "@/components/feedback/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { ActionButton } from "@/components/feedback/ActionButton";
import { ApiError } from "@/lib/api/errors";
import { formatDate } from "@/lib/format/date";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { SendPreviewDialog } from "./components/SendPreviewDialog";
import { WithdrawQuotationDialog } from "./components/WithdrawQuotationDialog";
import { ConvertQuotationDialog } from "./components/ConvertQuotationDialog";
import { LineEditDialog } from "./components/LineEditDialog";
import { QuotationLineCard } from "./components/QuotationLineCard";
import { useCopyToClipboard } from "@/lib/clipboard/useCopyToClipboard";
import { htmlToPlainText } from "@/lib/clipboard/htmlToPlainText";
import {
  useDeleteQuotationLine,
  useDuplicateQuotation,
  useHoldQuotationLine,
  useMarkQuotationManuallySent,
  useQuotation,
  useQuotationLines,
  useQuotationPreview,
  useReleaseQuotationLineHold,
} from "./hooks";
import {
  TERMINAL_QUOTATION_STATUSES,
  quotationStatusLabel,
  type QuotationDetail,
  type QuotationLine,
} from "./schemas";

type DialogKind =
  | "send"
  | "withdraw"
  | "convert"
  | "delete-line"
  | "edit-line"
  | "hold-line"
  | "release-hold-line"
  | null;

interface LinesSectionProps {
  quotation: QuotationDetail;
  canWrite: boolean;
  onEdit: (line: QuotationLine) => void;
  onDelete: (line: QuotationLine) => void;
  onHold: (line: QuotationLine) => void;
  onReleaseHold: (line: QuotationLine) => void;
  onBook: (line: QuotationLine) => void;
}

function LinesSection({
  quotation,
  canWrite,
  onEdit,
  onDelete,
  onHold,
  onReleaseHold,
  onBook,
}: LinesSectionProps) {
  const { t } = useTranslation("quotations");
  const lines = useQuotationLines(quotation.id);

  if (lines.isLoading) {
    return <Skeleton className="h-32 w-full" />;
  }
  if (lines.isError) {
    return (
      <ErrorState
        description={t("detail.lines.errors.load_failed")}
        onRetry={() => lines.refetch()}
        retrying={lines.isFetching}
      />
    );
  }
  const results = lines.data?.results ?? [];
  if (results.length === 0) {
    return <EmptyState title={t("detail.lines.empty")} />;
  }
  // Holds may be placed while the quote is still being worked (draft/sent);
  // releasing is always allowed — a hold can outlive its quotation. Booking
  // requires the guest to have actually received the quote (sent).
  const quoteEditable = quotation.status === "draft" || quotation.status === "sent";
  const canBook = canWrite && quotation.status === "sent";
  return (
    <ul className="space-y-2">
      {results.map((line: QuotationLine) => (
        <QuotationLineCard
          key={line.id}
          line={line}
          canWrite={canWrite}
          quoteEditable={quoteEditable}
          canBook={canBook}
          onEdit={() => onEdit(line)}
          onDelete={() => onDelete(line)}
          onHold={() => onHold(line)}
          onReleaseHold={() => onReleaseHold(line)}
          onBook={() => onBook(line)}
        />
      ))}
    </ul>
  );
}

interface RailSummaryProps {
  quotation: QuotationDetail;
  canWrite: boolean;
  onOpen: (dialog: DialogKind) => void;
  onDuplicate: () => void;
  duplicating: boolean;
  onCopy: () => void;
  copying: boolean;
  copyReason: string | null;
}

function RailSummary({
  quotation,
  canWrite,
  onOpen,
  onDuplicate,
  duplicating,
  onCopy,
  copying,
  copyReason,
}: RailSummaryProps) {
  const { t } = useTranslation("quotations");

  const isDraft = quotation.status === "draft";
  const isSent = quotation.status === "sent";
  const isTerminal = (TERMINAL_QUOTATION_STATUSES as readonly string[]).includes(quotation.status);

  const roleReason = canWrite ? null : t("detail.actions.disable_reasons.no_role");
  const sendReason = roleReason ?? (isDraft ? null : t("detail.actions.disable_reasons.not_draft"));
  const withdrawReason =
    roleReason ?? (isTerminal ? t("detail.actions.disable_reasons.terminal") : null);

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-foreground font-serif text-lg font-semibold">{quotation.reference}</h2>
        <p className="text-muted-foreground text-sm">{t("detail.summary.title")}</p>
      </div>
      <StatusBadge status={quotation.status} label={quotationStatusLabel(quotation.status)} />
      <FactList>
        <FactRow
          label={t("detail.summary.enquiry")}
          value={
            quotation.enquiry_reference ??
            (quotation.enquiry != null ? `#${quotation.enquiry}` : "—")
          }
        />
        <FactRow
          label={t("detail.summary.guest")}
          value={quotation.guest_name ?? (quotation.guest != null ? `#${quotation.guest}` : "—")}
        />
        <FactRow
          label={t("detail.summary.agent")}
          value={quotation.agent_name ?? (quotation.agent != null ? `#${quotation.agent}` : "—")}
        />
        <FactRow
          label={t("detail.summary.expires_at")}
          value={formatDate(quotation.expires_at ?? null)}
        />
        <FactRow
          label={t("detail.summary.created_at")}
          value={formatDate(quotation.created_at ?? null)}
        />
      </FactList>
      <div className="space-y-2">
        <p className="text-muted-foreground text-xs font-semibold tracking-wider uppercase">
          {t("detail.actions.section_label")}
        </p>
        <ActionButton
          label={isSent ? t("detail.actions.send_again") : t("detail.actions.send")}
          onClick={() => onOpen("send")}
          disableReason={sendReason}
        />
        <ActionButton
          label={copying ? t("detail.actions.copying") : t("detail.actions.copy_to_clipboard")}
          onClick={onCopy}
          disableReason={sendReason ?? copyReason}
          disabled={copying}
        />
        <ActionButton
          label={duplicating ? t("detail.actions.duplicating") : t("detail.actions.duplicate")}
          onClick={onDuplicate}
          disableReason={roleReason ?? (duplicating ? t("detail.actions.duplicating") : null)}
        />
        <ActionButton
          label={t("detail.actions.withdraw")}
          onClick={() => onOpen("withdraw")}
          disableReason={withdrawReason}
          variant="destructive"
        />
      </div>
    </div>
  );
}

export function QuotationDetailLayout() {
  const { t } = useTranslation("quotations");
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const query = useQuotation(id);
  const canWrite = useHasReservationsRole();
  const duplicate = useDuplicateQuotation(query.data?.id ?? 0);
  const deleteLineMut = useDeleteQuotationLine(query.data?.id ?? 0);
  const holdLineMut = useHoldQuotationLine(query.data?.id ?? 0);
  const releaseHoldMut = useReleaseQuotationLineHold(query.data?.id ?? 0);
  const markManuallySent = useMarkQuotationManuallySent(query.data?.id ?? 0);
  const { copy } = useCopyToClipboard();
  // Prefetch the guest-facing preview so the rail "Copy" button can write to
  // the clipboard synchronously inside the click (no awaited fetch first,
  // which would lose the transient-activation window in Safari/Firefox).
  // Only worth fetching once we know the quotation id and the user can act.
  const previewQuery = useQuotationPreview(query.data?.id ?? 0, !!query.data && canWrite);

  const [dialog, setDialog] = useState<DialogKind>(null);
  const [activeLine, setActiveLine] = useState<QuotationLine | null>(null);
  const [copying, setCopying] = useState(false);

  if (query.isLoading) {
    return (
      <div className="space-y-4 p-6">
        <Skeleton className="h-8 w-1/3" />
        <Skeleton className="h-4 w-1/4" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (query.isError || !query.data) {
    const is404 = query.error instanceof ApiError && query.error.status === 404;
    return (
      <div className="p-6">
        <ErrorState
          title={is404 ? t("detail.errors.not_found") : t("detail.errors.load_failed")}
          description={
            is404
              ? t("detail.errors.not_found_description")
              : t("detail.errors.load_failed_description")
          }
          onRetry={is404 ? undefined : () => query.refetch()}
        />
      </div>
    );
  }

  const quotation = query.data;

  const handleDuplicate = async () => {
    try {
      const clone = await duplicate.mutateAsync();
      toast.success(t("detail.dialogs.duplicate.toasts.success"));
      navigate(`/enquiries/quotes/${clone.id}`);
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.detail || t("detail.dialogs.duplicate.toasts.failed")
          : t("detail.dialogs.duplicate.toasts.failed");
      toast.error(message);
    }
  };

  // Path B (Outlook): copy the PREFETCHED guest-facing HTML, then record the
  // SENT state so it mirrors the Path A bookkeeping. The clipboard write MUST
  // stay synchronous within the click — awaiting a fetch first would lose the
  // transient-activation window in Safari/Firefox (NotAllowedError). The
  // button is disabled until `previewQuery.data` is cached, so it's present.
  const previewHtml = previewQuery.data?.html ?? null;
  const handleCopyToClipboard = async () => {
    if (!previewHtml) return;
    setCopying(true);
    // Synchronous: reach clipboard.write inside the click's user activation.
    const copied = copy(previewHtml, htmlToPlainText(previewHtml));
    try {
      const ok = await copied;
      if (!ok) {
        toast.error(t("detail.dialogs.send_preview.toasts.copy_failed"));
        return;
      }
      await markManuallySent.mutateAsync();
      toast.success(t("detail.dialogs.send_preview.toasts.copied"));
    } catch (error) {
      const message =
        error instanceof ApiError && error.detail
          ? error.detail
          : t("detail.dialogs.send_preview.toasts.copy_failed");
      toast.error(message);
    } finally {
      setCopying(false);
    }
  };

  const closeLineDialog = () => {
    setDialog(null);
    setActiveLine(null);
  };

  const handleHoldLine = async () => {
    if (!activeLine) return;
    try {
      await holdLineMut.mutateAsync(activeLine.id);
      toast.success(t("detail.dialogs.line_hold.toasts.success"));
      closeLineDialog();
    } catch (error) {
      // The 409 detail names the villa and whoever holds the dates — show it
      // verbatim; anything else gets the generic failure copy.
      const message =
        error instanceof ApiError
          ? error.detail || t("detail.dialogs.line_hold.toasts.failed")
          : t("detail.dialogs.line_hold.toasts.failed");
      toast.error(message);
      closeLineDialog();
    }
  };

  const handleReleaseHold = async () => {
    if (!activeLine) return;
    try {
      await releaseHoldMut.mutateAsync(activeLine.id);
      toast.success(t("detail.dialogs.line_release_hold.toasts.success"));
      closeLineDialog();
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.detail || t("detail.dialogs.line_release_hold.toasts.failed")
          : t("detail.dialogs.line_release_hold.toasts.failed");
      toast.error(message);
      closeLineDialog();
    }
  };

  const handleDeleteLine = async () => {
    if (!activeLine) return;
    try {
      await deleteLineMut.mutateAsync(activeLine.id);
      toast.success(t("detail.dialogs.line_delete.toasts.success"));
      setDialog(null);
      setActiveLine(null);
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.detail || t("detail.dialogs.line_delete.toasts.failed")
          : t("detail.dialogs.line_delete.toasts.failed");
      toast.error(message);
    }
  };

  return (
    <div>
      <PageHeader
        title={quotation.reference}
        breadcrumbs={[
          { label: t("detail.breadcrumb_root") },
          { label: t("common:nav.quotes"), to: "/enquiries/quotes" },
          { label: quotation.reference },
        ]}
      />

      <TwoColumn
        rightRail={
          <RailSummary
            quotation={quotation}
            canWrite={canWrite}
            onOpen={setDialog}
            onDuplicate={handleDuplicate}
            duplicating={duplicate.isPending}
            onCopy={handleCopyToClipboard}
            copying={copying || markManuallySent.isPending}
            copyReason={previewHtml ? null : t("detail.actions.disable_reasons.preview_loading")}
          />
        }
      >
        <section className="space-y-3">
          <h3 className="text-foreground text-base font-semibold">{t("detail.lines.title")}</h3>
          <LinesSection
            quotation={quotation}
            canWrite={canWrite}
            onEdit={(line) => {
              setActiveLine(line);
              setDialog("edit-line");
            }}
            onDelete={(line) => {
              setActiveLine(line);
              setDialog("delete-line");
            }}
            onHold={(line) => {
              setActiveLine(line);
              setDialog("hold-line");
            }}
            onReleaseHold={(line) => {
              setActiveLine(line);
              setDialog("release-hold-line");
            }}
            onBook={(line) => {
              setActiveLine(line);
              setDialog("convert");
            }}
          />
        </section>
      </TwoColumn>

      {dialog === "send" ? (
        <SendPreviewDialog
          open
          onOpenChange={(open) => !open && setDialog(null)}
          quotation={quotation}
        />
      ) : null}
      {dialog === "withdraw" ? (
        <WithdrawQuotationDialog
          open
          onOpenChange={(open) => !open && setDialog(null)}
          quotation={quotation}
        />
      ) : null}
      {dialog === "convert" ? (
        <ConvertQuotationDialog
          open
          onOpenChange={(open) => {
            if (!open) {
              setDialog(null);
              setActiveLine(null);
            }
          }}
          quotation={quotation}
          initialLineId={activeLine?.id ?? null}
        />
      ) : null}
      {dialog === "edit-line" && activeLine ? (
        <LineEditDialog
          open
          onOpenChange={(open) => {
            if (!open) {
              setDialog(null);
              setActiveLine(null);
            }
          }}
          quotationId={quotation.id}
          line={activeLine}
        />
      ) : null}
      <ConfirmDialog
        open={dialog === "hold-line"}
        onOpenChange={(open) => !open && closeLineDialog()}
        onConfirm={handleHoldLine}
        title={t("detail.dialogs.line_hold.title")}
        description={t("detail.dialogs.line_hold.description", {
          property: activeLine?.property_name ?? `#${activeLine?.property ?? "—"}`,
          from: formatDate(activeLine?.date_from ?? null),
          to: formatDate(activeLine?.date_to ?? null),
        })}
        confirmLabel={t("detail.dialogs.line_hold.confirm")}
        busy={holdLineMut.isPending}
      />
      <ConfirmDialog
        open={dialog === "release-hold-line"}
        onOpenChange={(open) => !open && closeLineDialog()}
        onConfirm={handleReleaseHold}
        title={t("detail.dialogs.line_release_hold.title")}
        description={t("detail.dialogs.line_release_hold.description", {
          property: activeLine?.property_name ?? `#${activeLine?.property ?? "—"}`,
          from: formatDate(activeLine?.date_from ?? null),
          to: formatDate(activeLine?.date_to ?? null),
        })}
        confirmLabel={t("detail.dialogs.line_release_hold.confirm")}
        busy={releaseHoldMut.isPending}
      />
      <ConfirmDialog
        open={dialog === "delete-line"}
        onOpenChange={(open) => {
          if (!open) {
            setDialog(null);
            setActiveLine(null);
          }
        }}
        onConfirm={handleDeleteLine}
        title={t("detail.dialogs.line_delete.title")}
        description={t("detail.dialogs.line_delete.description")}
        confirmLabel={t("detail.dialogs.line_delete.confirm")}
        busy={deleteLineMut.isPending}
      />
    </div>
  );
}
