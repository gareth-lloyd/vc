import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { ApiError } from "@/lib/api/errors";
import { useUpdateQuotationLine } from "../hooks";
import {
  quotationLineWriteInputSchema,
  type QuotationLine,
  type QuotationLineWriteInput,
} from "../schemas";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  quotationId: number;
  line: QuotationLine;
}

// Decimal fields round-trip as strings to feed text inputs without float
// drift; `null`/`undefined` collapse to an empty string.
function decimalToInput(value: string | number | null | undefined): string {
  if (value == null) return "";
  return String(value);
}

function defaultsFromLine(line: QuotationLine): QuotationLineWriteInput {
  return {
    property: (line.property ?? 0) as number,
    date_from: line.date_from ?? "",
    date_to: line.date_to ?? "",
    adults: line.adults ?? 0,
    children: line.children ?? 0,
    discount: decimalToInput(line.discount),
    inclusions: line.inclusions ?? "",
    is_manual: line.is_manual ?? false,
    total: decimalToInput(line.total),
    price_override_reason: line.price_override_reason ?? "",
    notes: line.notes ?? "",
  };
}

export function LineEditDialog({ open, onOpenChange, quotationId, line }: Props) {
  const { t } = useTranslation("quotations");
  const update = useUpdateQuotationLine(quotationId);
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  const form = useForm<QuotationLineWriteInput>({
    resolver: zodResolver(quotationLineWriteInputSchema),
    defaultValues: defaultsFromLine(line),
  });

  useEffect(() => {
    if (open) {
      form.reset(defaultsFromLine(line));
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, line.id]);

  const isManual = form.watch("is_manual");

  const handleSubmit = async (values: QuotationLineWriteInput) => {
    setTopLevelError(null);
    // Build the wire body explicitly. Decimal fields can't take an empty
    // string, so we only include `total`/`price_override_reason` on the
    // manual path; the server prices non-manual lines and applies `discount`.
    const body: Partial<QuotationLineWriteInput> = {
      property: values.property,
      date_from: values.date_from,
      date_to: values.date_to,
      adults: values.adults,
      children: values.children,
      discount: (values.discount ?? "").trim() || "0",
      inclusions: values.inclusions ?? "",
      is_manual: values.is_manual,
      notes: values.notes,
    };
    if (values.is_manual) {
      body.total = (values.total ?? "").trim();
      body.price_override_reason = values.price_override_reason ?? "";
    }
    try {
      await update.mutateAsync({ lineId: line.id, body });
      toast.success(t("detail.dialogs.line_edit.toasts.success"));
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        setTopLevelError(detail);
      } else {
        toast.error(t("detail.dialogs.line_edit.toasts.failed"));
      }
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !update.isPending && onOpenChange(o)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("detail.dialogs.line_edit.title")}</DialogTitle>
          <DialogDescription>{t("detail.dialogs.line_edit.description")}</DialogDescription>
        </DialogHeader>

        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="qle-date-from">{t("builder.criteria.date_from")}</Label>
              <Input id="qle-date-from" type="date" {...form.register("date_from")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="qle-date-to">{t("builder.criteria.date_to")}</Label>
              <Input id="qle-date-to" type="date" {...form.register("date_to")} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="qle-adults">{t("builder.criteria.adults")}</Label>
              <Input
                id="qle-adults"
                type="number"
                min={1}
                {...form.register("adults", { valueAsNumber: true })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="qle-children">{t("builder.criteria.children")}</Label>
              <Input
                id="qle-children"
                type="number"
                min={0}
                {...form.register("children", { valueAsNumber: true })}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="qle-discount">{t("detail.dialogs.line_edit.discount_label")}</Label>
              <Input
                id="qle-discount"
                type="text"
                inputMode="decimal"
                {...form.register("discount")}
              />
              <p className="text-muted-foreground text-xs">
                {t("detail.dialogs.line_edit.discount_hint")}
              </p>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="qle-inclusions">{t("detail.dialogs.line_edit.inclusions_label")}</Label>
            <Textarea
              id="qle-inclusions"
              rows={2}
              placeholder={t("detail.dialogs.line_edit.inclusions_placeholder")}
              {...form.register("inclusions")}
            />
          </div>

          <div className="space-y-2">
            <label className="flex cursor-pointer items-center gap-2 text-sm">
              <Checkbox
                checked={!!form.watch("is_manual")}
                onCheckedChange={(v) => form.setValue("is_manual", v === true)}
              />
              <span>{t("detail.dialogs.line_edit.manual_label")}</span>
            </label>
            <p className="text-muted-foreground text-xs">
              {t("detail.dialogs.line_edit.manual_hint")}
            </p>
          </div>

          {isManual ? (
            <>
              <div className="space-y-2">
                <Label htmlFor="qle-total">{t("detail.dialogs.line_edit.total_label")}</Label>
                <Input id="qle-total" type="text" inputMode="decimal" {...form.register("total")} />
                {form.formState.errors.total ? (
                  <p className="text-destructive text-xs">{form.formState.errors.total.message}</p>
                ) : null}
              </div>
              <div className="space-y-2">
                <Label htmlFor="qle-reason">
                  {t("detail.dialogs.line_edit.price_override_reason_label")}
                </Label>
                <Textarea
                  id="qle-reason"
                  rows={2}
                  placeholder={t("detail.dialogs.line_edit.price_override_reason_placeholder")}
                  {...form.register("price_override_reason")}
                />
                {form.formState.errors.price_override_reason ? (
                  <p className="text-destructive text-xs">
                    {form.formState.errors.price_override_reason.message}
                  </p>
                ) : null}
              </div>
            </>
          ) : null}

          <div className="space-y-2">
            <Label htmlFor="qle-notes">{t("detail.dialogs.line_edit.notes_label")}</Label>
            <Textarea id="qle-notes" rows={3} {...form.register("notes")} />
          </div>

          <FormErrorAlert message={topLevelError} />

          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={update.isPending}
            >
              {t("detail.dialogs.line_edit.cancel")}
            </Button>
            <Button type="submit" disabled={update.isPending}>
              {update.isPending
                ? t("detail.dialogs.line_edit.saving")
                : t("detail.dialogs.line_edit.confirm")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
