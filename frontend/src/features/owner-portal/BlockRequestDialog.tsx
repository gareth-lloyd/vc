import { useEffect, useMemo, useState } from "react";
import { useController, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { addMonths, format, startOfMonth } from "date-fns";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { DateRangeField } from "@/components/form/DateRangeField";
import { disabledDaysFromCells } from "@/components/form/disabledDays";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { ApiError } from "@/lib/api/errors";
import { nightsSummaryArgs } from "@/lib/format/date";
import { useCreateBlockRequest, useOwnerPropertyCalendar } from "./hooks";
import {
  blockRequestWriteInputSchema,
  ownerBlockKindSchema,
  type BlockRequestWriteInput,
} from "./schemas";

interface Props {
  propertyId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function defaults(propertyId: number): BlockRequestWriteInput {
  return { property: propertyId, date_from: "", date_to: "", kind: "owner_stay", notes: "" };
}

export function BlockRequestDialog({ propertyId, open, onOpenChange }: Props) {
  const { t } = useTranslation("owner");
  const form = useForm<BlockRequestWriteInput>({
    resolver: zodResolver(blockRequestWriteInputSchema),
    defaultValues: defaults(propertyId),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  const createMutation = useCreateBlockRequest();
  const kindCtrl = useController({ control: form.control, name: "kind" });

  useEffect(() => {
    if (open) {
      form.reset(defaults(propertyId));
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, propertyId]);

  const handleSubmit = async (values: BlockRequestWriteInput) => {
    setTopLevelError(null);
    try {
      await createMutation.mutateAsync(values);
      toast.success(t("blocks.toasts.created"));
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        // A conflicting range now hard-fails with 409. Prefer a friendly,
        // actionable message over the backend's terse `detail`.
        setTopLevelError(t("blocks.errors.conflict"));
      } else if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        setTopLevelError(detail);
      } else {
        toast.error(t("common:errors.generic"));
      }
    }
  };

  const errors = form.formState.errors;

  // Grey out already-occupied days in the picker over a generous forward window.
  // The list is only consumed by the calendar popover, so defer the fetch until
  // the picker is first opened. The server still validates conflicts regardless;
  // this is a courtesy, not the guard.
  const [pickerOpened, setPickerOpened] = useState(false);
  const windowStart = useMemo(() => startOfMonth(new Date()), []);
  const calendar = useOwnerPropertyCalendar(
    pickerOpened ? propertyId : undefined,
    format(windowStart, "yyyy-MM-dd"),
    format(addMonths(windowStart, 18), "yyyy-MM-dd"),
  );
  const disabledDays = useMemo(
    () => disabledDaysFromCells(calendar.data?.cells ?? []),
    [calendar.data],
  );

  const summaryArgs = nightsSummaryArgs(form.watch("date_from"), form.watch("date_to"));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("blocks.dialog.title")}</DialogTitle>
          <DialogDescription>{t("blocks.dialog.description")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <DateRangeField
            control={form.control}
            fromName="date_from"
            toName="date_to"
            fromId="block-date-from"
            toId="block-date-to"
            fromLabel={t("blocks.fields.date_from")}
            toLabel={t("blocks.fields.date_to")}
            pickLabel={t("blocks.fields.pick_dates")}
            disabledDays={disabledDays}
            onPickerOpenChange={(open) => open && setPickerOpened(true)}
            fromError={errors.date_from ? t(errors.date_from.message ?? "") : undefined}
            toError={errors.date_to ? t(errors.date_to.message ?? "") : undefined}
          />

          {summaryArgs ? (
            <p className="text-muted-foreground text-sm" data-testid="block-nights-summary">
              {t("blocks.dialog.nights_summary", summaryArgs)}
            </p>
          ) : null}

          <div className="space-y-2">
            <Label htmlFor="block-kind">{t("blocks.fields.kind")}</Label>
            <Select value={kindCtrl.field.value} onValueChange={kindCtrl.field.onChange}>
              <SelectTrigger id="block-kind" aria-label={t("blocks.fields.kind")}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ownerBlockKindSchema.options.map((kind) => (
                  <SelectItem key={kind} value={kind}>
                    {t(`blocks.kind.${kind}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="block-notes">{t("blocks.fields.notes")}</Label>
            <Textarea id="block-notes" rows={3} {...form.register("notes")} />
          </div>

          <FormErrorAlert message={topLevelError} />

          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={createMutation.isPending}
            >
              {t("common:actions.cancel")}
            </Button>
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? t("common:actions.saving") : t("blocks.actions.submit")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
