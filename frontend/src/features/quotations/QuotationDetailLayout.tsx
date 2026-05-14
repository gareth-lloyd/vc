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
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ActionButton } from "@/components/feedback/ActionButton";
import { ApiError } from "@/lib/api/errors";
import { formatDate } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/money";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { SendQuotationDialog } from "./components/SendQuotationDialog";
import { WithdrawQuotationDialog } from "./components/WithdrawQuotationDialog";
import { LineEditDialog } from "./components/LineEditDialog";
import {
  useDeleteQuotationLine,
  useDuplicateQuotation,
  useQuotation,
  useQuotationLines,
} from "./hooks";
import { TERMINAL_QUOTATION_STATUSES, type QuotationDetail, type QuotationLine } from "./schemas";

type DialogKind = "send" | "withdraw" | "delete-line" | "edit-line" | null;

interface LinesSectionProps {
  quotation: QuotationDetail;
  canWrite: boolean;
  onEdit: (line: QuotationLine) => void;
  onDelete: (line: QuotationLine) => void;
}

function LinesSection({ quotation, canWrite, onEdit, onDelete }: LinesSectionProps) {
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
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t("detail.lines.columns.id")}</TableHead>
          <TableHead>{t("detail.lines.columns.property")}</TableHead>
          <TableHead>{t("detail.lines.columns.dates")}</TableHead>
          <TableHead>{t("detail.lines.columns.guests")}</TableHead>
          <TableHead className="text-right">{t("detail.lines.columns.total")}</TableHead>
          <TableHead>{t("detail.lines.columns.selected")}</TableHead>
          <TableHead className="text-right">{t("detail.lines.columns.actions")}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {results.map((line: QuotationLine) => (
          <TableRow key={line.id}>
            <TableCell className="font-mono text-xs">#{line.id}</TableCell>
            <TableCell>{line.property != null ? `#${line.property}` : "—"}</TableCell>
            <TableCell>
              {formatDate(line.date_from ?? null)} – {formatDate(line.date_to ?? null)}
            </TableCell>
            <TableCell>
              {line.adults}A{line.children ? ` · ${line.children}C` : ""}
            </TableCell>
            <TableCell className="text-right">
              {formatMoney(line.total ?? null, quotation.currency ?? null)}
            </TableCell>
            <TableCell>
              {line.is_selected ? t("detail.lines.selected_yes") : t("detail.lines.selected_no")}
            </TableCell>
            <TableCell className="text-right">
              <div className="flex justify-end gap-1">
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => onEdit(line)}
                  disabled={!canWrite}
                >
                  {t("detail.lines.actions.edit")}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => onDelete(line)}
                  disabled={!canWrite}
                >
                  {t("detail.lines.actions.remove")}
                </Button>
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

interface RailSummaryProps {
  quotation: QuotationDetail;
  canWrite: boolean;
  onOpen: (dialog: DialogKind) => void;
  onDuplicate: () => void;
  duplicating: boolean;
}

function RailSummary({ quotation, canWrite, onOpen, onDuplicate, duplicating }: RailSummaryProps) {
  const { t } = useTranslation("quotations");

  const isDraft = quotation.status === "draft";
  const isSent = quotation.status === "sent";
  const isTerminal = (TERMINAL_QUOTATION_STATUSES as readonly string[]).includes(quotation.status);

  const roleReason = canWrite ? null : t("detail.actions.disable_reasons.no_role");
  const sendReason = roleReason ?? (isDraft ? null : t("detail.actions.disable_reasons.not_draft"));
  const withdrawReason =
    roleReason ?? (isTerminal ? t("detail.actions.disable_reasons.terminal") : null);
  const convertReason = t("detail.actions.disable_reasons.convert_pending");

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-foreground text-lg font-semibold">{quotation.reference}</h2>
        <p className="text-muted-foreground text-sm">{t("detail.summary.title")}</p>
      </div>
      <StatusBadge status={quotation.status} />
      <FactList>
        <FactRow
          label={t("detail.summary.enquiry")}
          value={quotation.enquiry != null ? `#${quotation.enquiry}` : "—"}
        />
        <FactRow
          label={t("detail.summary.guest")}
          value={quotation.guest != null ? `#${quotation.guest}` : "—"}
        />
        <FactRow
          label={t("detail.summary.agent")}
          value={quotation.agent != null ? `#${quotation.agent}` : "—"}
        />
        <FactRow label={t("detail.summary.currency")} value={quotation.currency ?? "—"} />
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
          label={duplicating ? t("detail.actions.duplicating") : t("detail.actions.duplicate")}
          onClick={onDuplicate}
          disableReason={roleReason ?? (duplicating ? t("detail.actions.duplicating") : null)}
        />
        <ActionButton
          label={t("detail.actions.convert")}
          onClick={() => undefined}
          disableReason={convertReason}
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

  const [dialog, setDialog] = useState<DialogKind>(null);
  const [activeLine, setActiveLine] = useState<QuotationLine | null>(null);

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
      navigate(`/quotations/${clone.id}`);
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.detail || t("detail.dialogs.duplicate.toasts.failed")
          : t("detail.dialogs.duplicate.toasts.failed");
      toast.error(message);
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
          { label: t("detail.breadcrumb_list"), to: "/quotations" },
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
          />
        </section>
      </TwoColumn>

      {dialog === "send" ? (
        <SendQuotationDialog
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
