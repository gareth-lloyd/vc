import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api/errors";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { fieldErrorText } from "@/lib/forms/fieldError";
import { useCreateRatePeriod, useUpdateRatePeriod } from "../hooks";
import { ratePeriodWriteInputSchema, type RatePeriod, type RatePeriodWriteInput } from "../schemas";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";

interface CommonProps {
  ratePlanId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface CreateProps extends CommonProps {
  mode: "create";
}

interface EditProps extends CommonProps {
  mode: "edit";
  period: RatePeriod;
}

type RatePeriodFormDialogProps = CreateProps | EditProps;

function createDefaults(): RatePeriodWriteInput {
  return {
    name: "",
    date_from: "",
    date_to: "",
    min_nights: null,
    max_nights: null,
    is_active: true,
  };
}

function defaultsFromPeriod(period: RatePeriod): RatePeriodWriteInput {
  return {
    name: period.name ?? "",
    date_from: period.date_from,
    date_to: period.date_to,
    min_nights: period.min_nights ?? null,
    max_nights: period.max_nights ?? null,
    is_active: period.is_active ?? true,
  };
}

export function RatePeriodFormDialog(props: RatePeriodFormDialogProps) {
  const { ratePlanId, open, onOpenChange } = props;
  const { t } = useTranslation("properties");
  const isCreate = props.mode === "create";

  const form = useForm<RatePeriodWriteInput>({
    resolver: zodResolver(ratePeriodWriteInputSchema),
    defaultValues: isCreate ? createDefaults() : defaultsFromPeriod(props.period),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  const createMutation = useCreateRatePeriod(ratePlanId);
  const updateMutation = useUpdateRatePeriod(ratePlanId);
  const submitting = createMutation.isPending || updateMutation.isPending;

  useEffect(() => {
    if (open) {
      form.reset(isCreate ? createDefaults() : defaultsFromPeriod(props.period));
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? null : props.period.id]);

  const handleSubmit = async (values: RatePeriodWriteInput) => {
    setTopLevelError(null);
    try {
      if (isCreate) {
        await createMutation.mutateAsync(values);
        toast.success(t("pricing.rate_period.toasts.created"));
      } else {
        await updateMutation.mutateAsync({ periodId: props.period.id, input: values });
        toast.success(t("pricing.rate_period.toasts.updated"));
      }
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        setTopLevelError(detail);
      } else {
        toast.error(
          isCreate
            ? t("pricing.rate_period.toasts.create_failed")
            : t("pricing.rate_period.toasts.update_failed"),
        );
      }
    }
  };

  const isActive = form.watch("is_active") ?? true;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isCreate
              ? t("pricing.rate_period.dialog.create_title")
              : t("pricing.rate_period.dialog.edit_title")}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="rate-period-name">{t("pricing.rate_period.dialog.fields.name")}</Label>
            <Input
              id="rate-period-name"
              placeholder={t("pricing.rate_period.dialog.fields.name_placeholder")}
              {...form.register("name")}
            />
            {form.formState.errors.name ? (
              <p className="text-destructive text-sm" role="alert">
                {fieldErrorText(t, form.formState.errors.name.message)}
              </p>
            ) : null}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="rate-period-date-from">
                {t("pricing.rate_period.dialog.fields.date_from")}
              </Label>
              <Input id="rate-period-date-from" type="date" {...form.register("date_from")} />
              {form.formState.errors.date_from ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.date_from.message)}
                </p>
              ) : null}
            </div>

            <div className="space-y-2">
              <Label htmlFor="rate-period-date-to">
                {t("pricing.rate_period.dialog.fields.date_to")}
              </Label>
              <Input id="rate-period-date-to" type="date" {...form.register("date_to")} />
              {form.formState.errors.date_to ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.date_to.message)}
                </p>
              ) : null}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="rate-period-min-nights">
                {t("pricing.rate_period.dialog.fields.min_nights")}
              </Label>
              <Input
                id="rate-period-min-nights"
                type="number"
                min={1}
                placeholder={t("pricing.rate_period.dialog.fields.nights_inherit_placeholder")}
                {...form.register("min_nights", {
                  setValueAs: (v) => (v === "" || v == null ? null : Number(v)),
                })}
              />
              {form.formState.errors.min_nights ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.min_nights.message)}
                </p>
              ) : null}
            </div>

            <div className="space-y-2">
              <Label htmlFor="rate-period-max-nights">
                {t("pricing.rate_period.dialog.fields.max_nights")}
              </Label>
              <Input
                id="rate-period-max-nights"
                type="number"
                min={1}
                placeholder={t("pricing.rate_period.dialog.fields.nights_inherit_placeholder")}
                {...form.register("max_nights", {
                  setValueAs: (v) => (v === "" || v == null ? null : Number(v)),
                })}
              />
              {form.formState.errors.max_nights ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.max_nights.message)}
                </p>
              ) : null}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Checkbox
              id="rate-period-is-active"
              checked={isActive}
              onCheckedChange={(v) => form.setValue("is_active", v === true)}
            />
            <Label htmlFor="rate-period-is-active">
              {t("pricing.rate_period.dialog.fields.is_active")}
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
              {t("pricing.rate_period.dialog.actions.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting
                ? t("pricing.rate_period.dialog.actions.saving")
                : t("pricing.rate_period.dialog.actions.save")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
