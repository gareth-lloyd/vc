import { useEffect, useMemo, useState } from "react";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { addMonths, format, startOfMonth } from "date-fns";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
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
import { ApiError } from "@/lib/api/errors";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { nightsSummaryArgs } from "@/lib/format/date";
import {
  useCreatePropertyBlock,
  usePropertyAvailabilityCalendar,
  useUpdatePropertyBlock,
} from "../hooks";
import {
  AVAILABILITY_BLOCK_REASONS,
  availabilityBlockWriteInputSchema,
  type AvailabilityBlockWriteInput,
} from "../schemas";

export interface EditableBlock {
  id: number;
  reason: (typeof AVAILABILITY_BLOCK_REASONS)[number];
  date_from: string;
  date_to: string;
  notes: string;
}

interface CommonProps {
  propertyId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface CreateProps extends CommonProps {
  mode: "create";
}

interface EditProps extends CommonProps {
  mode: "edit";
  block: EditableBlock;
}

type AvailabilityBlockFormDialogProps = CreateProps | EditProps;

const CREATE_DEFAULTS: AvailabilityBlockWriteInput = {
  reason: "manual",
  date_from: "",
  date_to: "",
  notes: "",
};

function defaultsFromBlock(block: EditableBlock): AvailabilityBlockWriteInput {
  return {
    reason: block.reason,
    date_from: block.date_from,
    date_to: block.date_to,
    notes: block.notes ?? "",
  };
}

export function AvailabilityBlockFormDialog(props: AvailabilityBlockFormDialogProps) {
  const { propertyId, open, onOpenChange } = props;
  const { t } = useTranslation("properties");
  const isCreate = props.mode === "create";

  const form = useForm<AvailabilityBlockWriteInput>({
    resolver: zodResolver(availabilityBlockWriteInputSchema),
    defaultValues: isCreate ? CREATE_DEFAULTS : defaultsFromBlock(props.block),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  const createMutation = useCreatePropertyBlock(propertyId);
  const updateMutation = useUpdatePropertyBlock(propertyId);
  const submitting = createMutation.isPending || updateMutation.isPending;

  useEffect(() => {
    if (open) {
      form.reset(isCreate ? CREATE_DEFAULTS : defaultsFromBlock(props.block));
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? null : props.block.id]);

  const handleSubmit = async (values: AvailabilityBlockWriteInput) => {
    setTopLevelError(null);
    try {
      if (isCreate) {
        await createMutation.mutateAsync(values);
        toast.success(t("availability.toasts.created"));
      } else {
        await updateMutation.mutateAsync({ blockId: props.block.id, input: values });
        toast.success(t("availability.toasts.updated"));
      }
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        setTopLevelError(detail);
      } else {
        toast.error(
          isCreate
            ? t("availability.toasts.create_failed")
            : t("availability.toasts.update_failed"),
        );
      }
    }
  };

  const reason = form.watch("reason");

  // Grey out already-occupied days over a forward window. In edit mode the block
  // being edited must stay selectable, so exclude its own cells (by block_id).
  // The list only feeds the calendar popover, so defer the fetch until it opens.
  const editingBlockId = isCreate ? null : props.block.id;
  const [pickerOpened, setPickerOpened] = useState(false);
  const windowStart = useMemo(() => startOfMonth(new Date()), []);
  const calendar = usePropertyAvailabilityCalendar(
    pickerOpened ? propertyId : undefined,
    format(windowStart, "yyyy-MM-dd"),
    format(addMonths(windowStart, 18), "yyyy-MM-dd"),
  );
  const disabledDays = useMemo(
    () => disabledDaysFromCells(calendar.data?.cells ?? [], editingBlockId),
    [calendar.data, editingBlockId],
  );

  const summaryArgs = nightsSummaryArgs(form.watch("date_from"), form.watch("date_to"));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isCreate
              ? t("availability.block_dialog.create_title")
              : t("availability.block_dialog.edit_title")}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="block-reason">{t("availability.block_dialog.fields.reason")}</Label>
            <Select
              value={reason}
              onValueChange={(v) =>
                form.setValue("reason", v as AvailabilityBlockWriteInput["reason"])
              }
            >
              <SelectTrigger id="block-reason">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {AVAILABILITY_BLOCK_REASONS.map((r) => (
                  <SelectItem key={r} value={r}>
                    {t(`availability.block_dialog.reasons.${r}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <DateRangeField
            control={form.control}
            fromName="date_from"
            toName="date_to"
            fromId="block-from"
            toId="block-to"
            fromLabel={t("availability.block_dialog.fields.date_from")}
            toLabel={t("availability.block_dialog.fields.date_to")}
            pickLabel={t("availability.block_dialog.fields.pick_dates")}
            disabledDays={disabledDays}
            onPickerOpenChange={(open) => open && setPickerOpened(true)}
            fromError={
              form.formState.errors.date_from
                ? String(form.formState.errors.date_from.message)
                : undefined
            }
            toError={
              form.formState.errors.date_to
                ? String(form.formState.errors.date_to.message)
                : undefined
            }
          />

          {summaryArgs ? (
            <p className="text-muted-foreground text-sm" data-testid="block-nights-summary">
              {t("availability.block_dialog.nights_summary", summaryArgs)}
            </p>
          ) : null}

          <div className="space-y-2">
            <Label htmlFor="block-notes">{t("availability.block_dialog.fields.notes")}</Label>
            <Textarea id="block-notes" rows={2} {...form.register("notes")} />
          </div>

          <FormErrorAlert message={topLevelError} />

          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              {t("availability.block_dialog.actions.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting
                ? t("availability.block_dialog.actions.saving")
                : t("availability.block_dialog.actions.save")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
