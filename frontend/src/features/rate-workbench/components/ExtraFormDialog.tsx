import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { MoneyInput } from "@/components/ui/money-input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/errors";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { fieldErrorText } from "@/lib/forms/fieldError";
import { currencyAdornment } from "@/lib/format/money";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { useCreateExtra, useUpdateExtra } from "../hooks";
import { extraWriteInputSchema, type ExtraWriteInput, type ExtraWritePayload } from "../schemas";
import type { Extra } from "@/features/properties/schemas";

interface CommonProps {
  propertyId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The property's resolved currency, shown as the amount adornment. */
  currencyCode?: string | null;
}

interface CreateProps extends CommonProps {
  mode: "create";
}

interface EditProps extends CommonProps {
  mode: "edit";
  entity: Extra;
}

type ExtraFormDialogProps = CreateProps | EditProps;

const CREATE_DEFAULTS: ExtraWriteInput = {
  name: "",
  description: "",
  kind: "",
  amount: "",
  is_mandatory: false,
  applies_from: "",
  applies_to: "",
  is_active: true,
};

function defaultsFromExtra(extra: Extra): ExtraWriteInput {
  return {
    name: extra.name,
    description: extra.description ?? "",
    kind: extra.kind ?? "",
    amount: extra.amount ?? "",
    is_mandatory: extra.is_mandatory ?? false,
    applies_from: extra.applies_from ?? "",
    applies_to: extra.applies_to ?? "",
    is_active: extra.is_active ?? true,
  };
}

function toPayload(values: ExtraWriteInput): ExtraWritePayload {
  // An empty amount/date is "unset" — send explicit `null`, never the empty
  // string the API rejects, and never `undefined` (which a PATCH omits, leaving
  // the old value in place).
  return {
    ...values,
    amount: values.amount ? values.amount : null,
    applies_from: values.applies_from || null,
    applies_to: values.applies_to || null,
  };
}

export function ExtraFormDialog(props: ExtraFormDialogProps) {
  const { propertyId, open, onOpenChange, currencyCode } = props;
  const { t } = useTranslation("properties");
  const isCreate = props.mode === "create";
  const amountAdornment = currencyAdornment(currencyCode);

  const form = useForm<ExtraWriteInput>({
    resolver: zodResolver(extraWriteInputSchema),
    defaultValues: isCreate ? CREATE_DEFAULTS : defaultsFromExtra(props.entity),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  const createMutation = useCreateExtra(propertyId);
  const updateMutation = useUpdateExtra(propertyId);
  const submitting = createMutation.isPending || updateMutation.isPending;

  useEffect(() => {
    if (open) {
      form.reset(isCreate ? CREATE_DEFAULTS : defaultsFromExtra(props.entity));
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? null : props.entity.id]);

  const handleSubmit = async (values: ExtraWriteInput) => {
    setTopLevelError(null);
    const body = toPayload(values);
    try {
      if (isCreate) {
        await createMutation.mutateAsync(body);
        toast.success(t("rate_workbench.inspector.toasts.created"));
      } else {
        await updateMutation.mutateAsync({ extraId: props.entity.id, input: body });
        toast.success(t("rate_workbench.inspector.toasts.updated"));
      }
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        setTopLevelError(detail);
      } else {
        toast.error(t("rate_workbench.inspector.toasts.save_failed"));
      }
    }
  };

  const isMandatory = form.watch("is_mandatory") ?? false;
  const isActive = form.watch("is_active") ?? true;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isCreate
              ? t("rate_workbench.inspector.extra_dialog.create_title")
              : t("rate_workbench.inspector.extra_dialog.edit_title")}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="extra-name">{t("rate_workbench.inspector.fields.name")}</Label>
            <Input id="extra-name" {...form.register("name")} />
            {form.formState.errors.name ? (
              <p className="text-destructive text-sm" role="alert">
                {fieldErrorText(t, form.formState.errors.name.message)}
              </p>
            ) : null}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="extra-kind">{t("rate_workbench.inspector.fields.kind")}</Label>
              <Input id="extra-kind" {...form.register("kind")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="extra-amount">{t("rate_workbench.inspector.fields.amount")}</Label>
              <MoneyInput
                id="extra-amount"
                inputMode="decimal"
                adornment={amountAdornment}
                {...form.register("amount")}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="extra-description">
              {t("rate_workbench.inspector.fields.description")}
            </Label>
            <Textarea id="extra-description" rows={2} {...form.register("description")} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="extra-applies-from">
                {t("rate_workbench.inspector.fields.applies_from")}
              </Label>
              <Input id="extra-applies-from" type="date" {...form.register("applies_from")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="extra-applies-to">
                {t("rate_workbench.inspector.fields.applies_to")}
              </Label>
              <Input id="extra-applies-to" type="date" {...form.register("applies_to")} />
              {form.formState.errors.applies_to ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.applies_to.message)}
                </p>
              ) : null}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Checkbox
              id="extra-is-mandatory"
              checked={isMandatory}
              onCheckedChange={(v) => form.setValue("is_mandatory", v === true)}
            />
            <Label htmlFor="extra-is-mandatory">
              {t("rate_workbench.inspector.fields.is_mandatory")}
            </Label>
          </div>

          <div className="flex items-center gap-2">
            <Checkbox
              id="extra-is-active"
              checked={isActive}
              onCheckedChange={(v) => form.setValue("is_active", v === true)}
            />
            <Label htmlFor="extra-is-active">
              {t("rate_workbench.inspector.fields.is_active")}
            </Label>
          </div>

          <FormErrorAlert message={topLevelError} />

          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              {t("rate_workbench.inspector.actions.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting
                ? t("rate_workbench.inspector.actions.saving")
                : t("rate_workbench.inspector.actions.save")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
