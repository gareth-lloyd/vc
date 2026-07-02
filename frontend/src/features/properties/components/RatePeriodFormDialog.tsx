import { useEffect, useRef, useState } from "react";
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
import { formatWeekRangeCompact, suggestRatePeriodEnd } from "@/lib/format/date";
import { useCreateRatePeriod, useUpdateRatePeriod } from "../hooks";
import { ratePeriodWriteInputSchema, type RatePeriod, type RatePeriodWriteInput } from "../schemas";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";

interface CommonProps {
  ratePlanId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Property changeover settings (GAP-025, reinstated by SMELL-019 at the
   * period grain) for the end-date suggestion. Both optional — no fixed
   * changeover means no suggestion. */
  changeoverDay?: string | null;
  minNightsRental?: number | null;
}

interface CreateProps extends CommonProps {
  mode: "create";
  /** Optional date prefills (e.g. the workbench seeds `date_from` as the day
   * after the plan's latest period, or a coverage gap's exact range). A
   * provided `date_to` always wins over the changeover suggestion. */
  initialValues?: { date_from?: string; date_to?: string };
}

interface EditProps extends CommonProps {
  mode: "edit";
  period: RatePeriod;
}

type RatePeriodFormDialogProps = CreateProps | EditProps;

function createDefaults(initialValues?: {
  date_from?: string;
  date_to?: string;
}): RatePeriodWriteInput {
  return {
    name: "",
    date_from: initialValues?.date_from ?? "",
    date_to: initialValues?.date_to ?? "",
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
  const { ratePlanId, open, onOpenChange, changeoverDay, minNightsRental } = props;
  const { t } = useTranslation("properties");
  const isCreate = props.mode === "create";
  const initialValues = props.mode === "create" ? props.initialValues : undefined;

  const form = useForm<RatePeriodWriteInput>({
    resolver: zodResolver(ratePeriodWriteInputSchema),
    defaultValues: isCreate ? createDefaults(initialValues) : defaultsFromPeriod(props.period),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  const createMutation = useCreateRatePeriod(ratePlanId);
  const updateMutation = useUpdateRatePeriod(ratePlanId);
  const submitting = createMutation.isPending || updateMutation.isPending;

  useEffect(() => {
    if (open) {
      form.reset(isCreate ? createDefaults(initialValues) : defaultsFromPeriod(props.period));
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? null : props.period.id]);

  // GAP-025 (reinstated by SMELL-019 at the period grain): when the property
  // changes over on a fixed weekday, suggest the period's end date as soon as
  // `date_from` is known — but never clobber a value the user typed (only fill
  // while `date_to` is empty or still holds our own last suggestion). Edit mode
  // keeps the stored value untouched.
  const dateFrom = form.watch("date_from");
  const lastSuggestionRef = useRef<string | null>(null);
  useEffect(() => {
    if (!isCreate || !dateFrom) return;
    const currentTo = form.getValues("date_to");
    if (currentTo && currentTo !== lastSuggestionRef.current) return;
    const suggested = suggestRatePeriodEnd(dateFrom, changeoverDay, minNightsRental);
    if (!suggested || suggested === currentTo) return;
    lastSuggestionRef.current = suggested;
    form.setValue("date_to", suggested, { shouldDirty: false, shouldValidate: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dateFrom, isCreate, changeoverDay, minNightsRental]);

  // GAP-059: the name is compulsory, so keep the fast create flows
  // one-keystroke by suggesting the date-span label once both dates are known
  // — same never-clobber rule as the end-date suggestion above (only fill
  // while `name` is empty or still holds our own last suggestion).
  const dateTo = form.watch("date_to");
  const lastNameSuggestionRef = useRef<string | null>(null);
  useEffect(() => {
    if (!isCreate || !dateFrom || !dateTo) return;
    const currentName = form.getValues("name");
    if (currentName && currentName !== lastNameSuggestionRef.current) return;
    const suggested = formatWeekRangeCompact(dateFrom, dateTo);
    if (suggested === "—" || suggested === currentName) return;
    lastNameSuggestionRef.current = suggested;
    form.setValue("name", suggested, { shouldDirty: false, shouldValidate: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dateFrom, dateTo, isCreate]);

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
