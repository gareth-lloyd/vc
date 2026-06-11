import { useEffect, useState } from "react";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/lib/api/errors";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { useCreateChangeOverRule, useUpdateChangeOverRule } from "../hooks";
import {
  PROPERTY_CHANGEOVER_DAYS,
  changeOverRuleWriteInputSchema,
  type ChangeOverRule,
  type ChangeOverRuleWriteInput,
} from "../schemas";
import { fieldErrorText } from "@/lib/forms/fieldError";

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
  rule: ChangeOverRule;
}

type ChangeoverRuleFormDialogProps = CreateProps | EditProps;

const CREATE_DEFAULTS: ChangeOverRuleWriteInput = {
  weekday: "sat",
  effective_from: "",
  effective_to: "",
  notes: "",
};

function defaultsFromRule(rule: ChangeOverRule): ChangeOverRuleWriteInput {
  return {
    weekday: rule.weekday,
    effective_from: rule.effective_from,
    effective_to: rule.effective_to,
    notes: rule.notes ?? "",
  };
}

export function ChangeoverRuleFormDialog(props: ChangeoverRuleFormDialogProps) {
  const { propertyId, open, onOpenChange } = props;
  const { t } = useTranslation("properties");
  const isCreate = props.mode === "create";

  const form = useForm<ChangeOverRuleWriteInput>({
    resolver: zodResolver(changeOverRuleWriteInputSchema),
    defaultValues: isCreate ? CREATE_DEFAULTS : defaultsFromRule(props.rule),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  const createMutation = useCreateChangeOverRule(propertyId);
  const updateMutation = useUpdateChangeOverRule(propertyId);
  const submitting = createMutation.isPending || updateMutation.isPending;

  useEffect(() => {
    if (open) {
      form.reset(isCreate ? CREATE_DEFAULTS : defaultsFromRule(props.rule));
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? null : props.rule.id]);

  const handleSubmit = async (values: ChangeOverRuleWriteInput) => {
    setTopLevelError(null);
    try {
      if (isCreate) {
        await createMutation.mutateAsync(values);
        toast.success(t("changeover.toasts.created"));
      } else {
        await updateMutation.mutateAsync({ ruleId: props.rule.id, input: values });
        toast.success(t("changeover.toasts.updated"));
      }
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        setTopLevelError(detail);
      } else {
        toast.error(
          isCreate ? t("changeover.toasts.create_failed") : t("changeover.toasts.update_failed"),
        );
      }
    }
  };

  const weekday = form.watch("weekday");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isCreate ? t("changeover.dialog.create_title") : t("changeover.dialog.edit_title")}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="changeover-weekday">{t("changeover.dialog.fields.weekday")}</Label>
            <Select
              value={weekday}
              onValueChange={(v) =>
                form.setValue("weekday", v as ChangeOverRuleWriteInput["weekday"])
              }
            >
              <SelectTrigger id="changeover-weekday">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PROPERTY_CHANGEOVER_DAYS.map((d) => (
                  <SelectItem key={d} value={d}>
                    {t(`changeover_days.${d}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="changeover-from">
                {t("changeover.dialog.fields.effective_from")}
              </Label>
              <Input id="changeover-from" type="date" {...form.register("effective_from")} />
              {form.formState.errors.effective_from ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.effective_from.message)}
                </p>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="changeover-to">{t("changeover.dialog.fields.effective_to")}</Label>
              <Input id="changeover-to" type="date" {...form.register("effective_to")} />
              {form.formState.errors.effective_to ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.effective_to.message)}
                </p>
              ) : null}
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="changeover-notes">{t("changeover.dialog.fields.notes")}</Label>
            <Textarea id="changeover-notes" rows={2} {...form.register("notes")} />
          </div>

          <FormErrorAlert message={topLevelError} />

          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              {t("changeover.dialog.actions.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting
                ? t("changeover.dialog.actions.saving")
                : t("changeover.dialog.actions.save")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
