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

function defaultsFromLine(line: QuotationLine): QuotationLineWriteInput {
  return {
    property: (line.property ?? 0) as number,
    date_from: line.date_from ?? "",
    date_to: line.date_to ?? "",
    adults: line.adults ?? 0,
    children: line.children ?? 0,
    is_manual: line.is_manual ?? false,
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

  const handleSubmit = async (values: QuotationLineWriteInput) => {
    setTopLevelError(null);
    try {
      await update.mutateAsync({ lineId: line.id, body: values });
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

          <div className="space-y-2">
            <Label htmlFor="qle-notes">{t("detail.dialogs.line_edit.notes_label")}</Label>
            <Textarea id="qle-notes" rows={3} {...form.register("notes")} />
          </div>

          {topLevelError ? (
            <div
              className="bg-destructive/10 text-destructive border-destructive/40 rounded-md border p-3 text-sm"
              role="alert"
            >
              {topLevelError}
            </div>
          ) : null}

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
