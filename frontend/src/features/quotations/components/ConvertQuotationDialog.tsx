import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { ApiError } from "@/lib/api/errors";
import { formatDate } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/money";
import { useConvertQuotation, useQuotationLines } from "../hooks";
import { ChangeoverShiftedNote } from "./ChangeoverShiftedNote";
import type { QuotationDetail, QuotationLine } from "../schemas";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  quotation: QuotationDetail;
  /** Pin the initially-selected line (the per-row Book action); falls back
   * to the accepted line, then the first. */
  initialLineId?: number | null;
}

type PaymentMethod = "card" | "bank_transfer";

const PAYMENT_METHODS: readonly PaymentMethod[] = ["card", "bank_transfer"] as const;

function pickInitialLineId(
  lines: QuotationLine[] | undefined,
  preferred?: number | null,
): number | null {
  if (!lines || lines.length === 0) return null;
  if (preferred != null && lines.some((l) => l.id === preferred)) return preferred;
  return (lines.find((l) => l.is_selected) ?? lines[0]).id;
}

export function ConvertQuotationDialog({ open, onOpenChange, quotation, initialLineId }: Props) {
  const { t } = useTranslation("quotations");
  const navigate = useNavigate();
  const convert = useConvertQuotation(quotation);
  const linesQuery = useQuotationLines(quotation.id);
  const lines = linesQuery.data?.results;

  const [lineId, setLineId] = useState<number | null>(null);
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>("card");
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  const initialisedRef = useRef(false);

  useEffect(() => {
    if (!open) {
      // Full reset on close — next open starts from a clean slate.
      initialisedRef.current = false;
      setLineId(null);
      setPaymentMethod("card");
      setTopLevelError(null);
      return;
    }
    // Initialise the line selection exactly once per open session, so a
    // background `lines` refetch (window focus, reconnect) doesn't clobber
    // the operator's pick.
    if (!initialisedRef.current && lines) {
      initialisedRef.current = true;
      setLineId(pickInitialLineId(lines, initialLineId));
    }
  }, [open, lines, initialLineId]);

  const submit = async () => {
    if (lineId == null) return;
    setTopLevelError(null);
    try {
      const booking = await convert.mutateAsync({
        line: lineId,
        terms_accepted: true,
        payment_method: paymentMethod,
      });
      toast.success(t("detail.dialogs.convert.toasts.success"));
      onOpenChange(false);
      navigate(`/bookings/${booking.id}`);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        setTopLevelError(error.detail);
      } else {
        toast.error(t("detail.dialogs.convert.toasts.failed"));
      }
    }
  };

  const busy = convert.isPending;
  const linesLoading = linesQuery.isLoading;
  const linesEmpty = !linesLoading && (lines?.length ?? 0) === 0;

  return (
    <Dialog open={open} onOpenChange={(o) => !busy && onOpenChange(o)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("detail.dialogs.convert.title")}</DialogTitle>
          <DialogDescription>
            {t("detail.dialogs.convert.description", { reference: quotation.reference })}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">
              {t("detail.dialogs.convert.line_label")}
            </legend>
            {linesLoading ? (
              <p className="text-muted-foreground text-sm">
                {t("detail.dialogs.convert.loading_lines")}
              </p>
            ) : linesEmpty ? (
              <p className="text-muted-foreground text-sm">
                {t("detail.dialogs.convert.no_lines")}
              </p>
            ) : (
              <div className="max-h-[40dvh] space-y-2 overflow-y-auto pr-1" role="radiogroup">
                {(lines ?? []).map((line) => {
                  const inputId = `convert-line-${line.id}`;
                  return (
                    <Label
                      key={line.id}
                      htmlFor={inputId}
                      className="border-border hover:bg-muted/30 flex cursor-pointer items-start gap-3 rounded-md border p-3"
                    >
                      <input
                        id={inputId}
                        type="radio"
                        name="convert-line"
                        value={line.id}
                        checked={lineId === line.id}
                        onChange={() => setLineId(line.id)}
                        className="mt-1"
                      />
                      <span className="flex-1 space-y-1">
                        <span className="text-foreground block text-sm font-medium">
                          {line.property_name ??
                            (line.property != null
                              ? t("detail.dialogs.convert.property_with_id", { id: line.property })
                              : "—")}
                        </span>
                        <span className="text-muted-foreground block text-xs">
                          {formatDate(line.date_from ?? null)} – {formatDate(line.date_to ?? null)}{" "}
                          ·{" "}
                          {t("detail.dialogs.convert.guests", {
                            adults: line.adults ?? 0,
                            children: line.children ?? 0,
                          })}{" "}
                          · {formatMoney(line.total ?? null, line.currency ?? null)}
                        </span>
                        <ChangeoverShiftedNote
                          from={line.changeover_shifted_from}
                          className="italic"
                        />
                      </span>
                    </Label>
                  );
                })}
              </div>
            )}
          </fieldset>

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">
              {t("detail.dialogs.convert.payment_method_label")}
            </legend>
            <div className="flex gap-4" role="radiogroup">
              {PAYMENT_METHODS.map((method) => {
                const inputId = `convert-pm-${method}`;
                return (
                  <Label
                    key={method}
                    htmlFor={inputId}
                    className="flex cursor-pointer items-center gap-2 text-sm"
                  >
                    <input
                      id={inputId}
                      type="radio"
                      name="convert-payment-method"
                      value={method}
                      checked={paymentMethod === method}
                      onChange={() => setPaymentMethod(method)}
                    />
                    {t(`detail.dialogs.convert.payment_method_options.${method}`)}
                  </Label>
                );
              })}
            </div>
          </fieldset>

          <FormErrorAlert message={topLevelError} />
        </div>

        <div className="flex justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={busy}
          >
            {t("detail.dialogs.convert.cancel")}
          </Button>
          <Button
            type="button"
            onClick={() => submit()}
            disabled={busy || lineId == null || linesEmpty}
          >
            {busy ? t("detail.dialogs.convert.converting") : t("detail.dialogs.convert.confirm")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
