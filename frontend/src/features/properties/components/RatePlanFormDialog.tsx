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
import { asPriceBasis } from "@/lib/pricing/netGross";
import { useCreateRatePlan, usePropertySettings, useUpdateRatePlan } from "../hooks";
import {
  PROPERTY_PRICE_BASES,
  ratePlanWriteInputSchema,
  type RatePlan,
  type RatePlanWriteInput,
} from "../schemas";
import { CurrencyPicker } from "./CurrencyPicker";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
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
  season: RatePlan;
}

type RatePlanFormDialogProps = CreateProps | EditProps;

type PriceBasisValue = (typeof PROPERTY_PRICE_BASES)[number];

function createDefaults(
  currencyId: number | null,
  basis: PriceBasisValue = "gross",
): RatePlanWriteInput {
  return {
    name: "",
    currency: currencyId ?? 0,
    // GAP-035: a new season inherits the property's default basis
    // (prices_entered_as) so staff don't re-pick GROSS/NET every time. Still
    // freely editable per plan — basis is a per-plan property.
    price_basis: basis,
    effective_from: "",
    effective_to: "",
    is_active: true,
    notes: "",
  };
}

function defaultsFromSeason(season: RatePlan): RatePlanWriteInput {
  return {
    name: season.name,
    currency: season.currency ?? 0,
    price_basis: season.price_basis ?? "gross",
    effective_from: season.effective_from ?? "",
    effective_to: season.effective_to ?? "",
    is_active: season.is_active ?? true,
    notes: season.notes ?? "",
  };
}

export function RatePlanFormDialog(props: RatePlanFormDialogProps) {
  const { propertyId, open, onOpenChange } = props;
  const { t } = useTranslation("properties");
  const isCreate = props.mode === "create";

  const settings = usePropertySettings(propertyId);
  const defaultCurrency = settings.data?.currency ?? null;
  const defaultBasis = asPriceBasis(settings.data?.prices_entered_as_effective);

  const form = useForm<RatePlanWriteInput>({
    resolver: zodResolver(ratePlanWriteInputSchema),
    defaultValues: isCreate
      ? createDefaults(defaultCurrency, defaultBasis)
      : defaultsFromSeason(props.season),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  const createMutation = useCreateRatePlan(propertyId);
  const updateMutation = useUpdateRatePlan(propertyId);
  const submitting = createMutation.isPending || updateMutation.isPending;

  useEffect(() => {
    if (!open) return;
    // Create defaults (currency, basis) arrive asynchronously from
    // usePropertySettings, so this effect re-fires when they land to seed the
    // still-pristine form. Once the operator has started editing, skip the
    // re-seed — a late-arriving default must not form.reset() over their input
    // (the open-edge reset already ran while the form was clean).
    if (isCreate && form.formState.isDirty) return;
    form.reset(
      isCreate ? createDefaults(defaultCurrency, defaultBasis) : defaultsFromSeason(props.season),
    );
    setTopLevelError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? defaultCurrency : props.season.id, isCreate ? defaultBasis : null]);

  const handleSubmit = async (values: RatePlanWriteInput) => {
    setTopLevelError(null);
    // An empty To is "open-ended season" — send explicit `null`, never the
    // empty string the API rejects as an invalid date, and never `undefined`
    // (which a PATCH would omit, leaving a previously-set end date uncleared).
    const body: RatePlanWriteInput = {
      ...values,
      effective_to: values.effective_to || null,
    };
    try {
      if (isCreate) {
        await createMutation.mutateAsync(body);
        toast.success(t("pricing.seasons.toasts.created"));
      } else {
        await updateMutation.mutateAsync({ ratePlanId: props.season.id, input: body });
        toast.success(t("pricing.seasons.toasts.updated"));
      }
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        setTopLevelError(detail);
      } else {
        toast.error(
          isCreate
            ? t("pricing.seasons.toasts.create_failed")
            : t("pricing.seasons.toasts.update_failed"),
        );
      }
    }
  };

  const priceBasis = form.watch("price_basis");
  const isActive = form.watch("is_active") ?? true;
  const currencyValue = form.watch("currency");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isCreate
              ? t("pricing.seasons.dialog.create_title")
              : t("pricing.seasons.dialog.edit_title")}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="season-name">{t("pricing.seasons.dialog.fields.name")}</Label>
            <Input
              id="season-name"
              placeholder={t("pricing.seasons.dialog.fields.name_placeholder")}
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
              <Label htmlFor="season-currency">{t("pricing.seasons.dialog.fields.currency")}</Label>
              <CurrencyPicker
                id="season-currency"
                value={currencyValue}
                onChange={(v) => form.setValue("currency", v, { shouldValidate: true })}
                placeholder={t("pricing.seasons.dialog.fields.currency_placeholder")}
              />
              {form.formState.errors.currency ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.currency.message)}
                </p>
              ) : null}
            </div>

            <div className="space-y-2">
              <Label htmlFor="season-price-basis">
                {t("pricing.seasons.dialog.fields.price_basis")}
              </Label>
              <Select
                value={priceBasis}
                onValueChange={(v) =>
                  form.setValue("price_basis", v as (typeof PROPERTY_PRICE_BASES)[number])
                }
              >
                <SelectTrigger id="season-price-basis">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PROPERTY_PRICE_BASES.map((p) => (
                    <SelectItem key={p} value={p}>
                      {t(`pricing.seasons.price_basis.${p}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Inclusive [effective_from, effective_to] — the season covers both
              endpoint days. Two independent single-date inputs (not a range
              picker): a plan's effective window is typically very wide, where a
              two-endpoint calendar is the wrong control. effective_to is
              optional — an open-ended season is legal and common; a cleared To
              submits as `null` (see handleSubmit). */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="season-effective-from">
                {t("pricing.seasons.dialog.fields.effective_from")}
              </Label>
              <Input
                id="season-effective-from"
                type="date"
                {...form.register("effective_from")}
                aria-invalid={!!form.formState.errors.effective_from}
              />
              {form.formState.errors.effective_from ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.effective_from.message)}
                </p>
              ) : null}
            </div>

            <div className="space-y-2">
              <Label htmlFor="season-effective-to">
                {t("pricing.seasons.dialog.fields.effective_to")}
              </Label>
              <Input
                id="season-effective-to"
                type="date"
                {...form.register("effective_to")}
                aria-invalid={!!form.formState.errors.effective_to}
              />
              {form.formState.errors.effective_to ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.effective_to.message)}
                </p>
              ) : null}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Checkbox
              id="season-is-active"
              checked={isActive}
              onCheckedChange={(v) => form.setValue("is_active", v === true)}
            />
            <Label htmlFor="season-is-active">{t("pricing.seasons.dialog.fields.is_active")}</Label>
          </div>

          <div className="space-y-2">
            <Label htmlFor="season-notes">{t("pricing.seasons.dialog.fields.notes")}</Label>
            <Textarea id="season-notes" rows={2} {...form.register("notes")} />
          </div>

          <FormErrorAlert message={topLevelError} />

          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              {t("pricing.seasons.dialog.actions.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting
                ? t("pricing.seasons.dialog.actions.saving")
                : t("pricing.seasons.dialog.actions.save")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
