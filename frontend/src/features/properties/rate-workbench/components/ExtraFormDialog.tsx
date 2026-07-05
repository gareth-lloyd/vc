import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { DateRangePicker } from "@/components/form/DateRangePicker";
import { Input } from "@/components/ui/input";
import { MoneyInput } from "@/components/ui/money-input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/errors";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { fieldErrorText } from "@/lib/forms/fieldError";
import { currencyAdornment } from "@/lib/format/money";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { CurrencyPicker } from "@/features/properties/components/CurrencyPicker";
import { usePropertySettings } from "@/features/properties/hooks";
import { useCreateExtra, useUpdateExtra } from "../hooks";
import {
  EXTRA_CALCS,
  EXTRA_KINDS,
  extraWriteInputSchema,
  type ExtraWriteInput,
  type ExtraWritePayload,
} from "../schemas";
import { EnumSelect } from "./EnumSelect";
import type { Extra } from "@/features/properties/schemas";

interface CommonProps {
  propertyId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The property's resolved currency code, shown as the amount adornment. */
  currencyCode?: string | null;
  /**
   * The property's currency FK id (from a season), used to seed a new extra's
   * required `currency` when the settings row leaves the FK null.
   */
  defaultCurrencyId?: number | null;
  /**
   * Currency FK ids across the property's rate plans. The pricing engine only
   * applies extras matching the quote currency, so a currency outside this set
   * gets a non-blocking warning. Omit/empty when unknown — no warning then.
   */
  planCurrencyIds?: number[] | null;
}

interface CreateProps extends CommonProps {
  mode: "create";
}

interface EditProps extends CommonProps {
  mode: "edit";
  entity: Extra;
}

type ExtraFormDialogProps = CreateProps | EditProps;

// Sensible enum defaults so a new extra is savable without forcing a pick for
// every field (mirrors the season dialog defaulting price_basis). `currency`
// (0 → invalid) is re-seeded from the property's settings once they load.
function createDefaults(currencyId: number | null): ExtraWriteInput {
  return {
    name: "",
    description: "",
    kind: "other",
    calc: "fixed_per_stay",
    amount: "",
    currency: currencyId ?? 0,
    is_mandatory: false,
    applies_from: "",
    applies_to: "",
    is_active: true,
  };
}

function defaultsFromExtra(extra: Extra): ExtraWriteInput {
  return {
    name: extra.name,
    description: extra.description ?? "",
    kind: extra.kind ?? "other",
    calc: extra.calc ?? "fixed_per_stay",
    amount: extra.amount ?? "",
    currency: extra.currency ?? 0,
    is_mandatory: extra.is_mandatory ?? false,
    applies_from: extra.applies_from ?? "",
    applies_to: extra.applies_to ?? "",
    is_active: extra.is_active ?? true,
  };
}

function toPayload(values: ExtraWriteInput): ExtraWritePayload {
  // Only the genuinely-nullable date columns collapse to `null`; `amount` and
  // `currency` are required (the schema guarantees they're set).
  return {
    ...values,
    applies_from: values.applies_from || null,
    applies_to: values.applies_to || null,
  };
}

export function ExtraFormDialog(props: ExtraFormDialogProps) {
  const { propertyId, open, onOpenChange, currencyCode, defaultCurrencyId, planCurrencyIds } =
    props;
  const { t } = useTranslation("properties");
  const isCreate = props.mode === "create";
  const amountAdornment = currencyAdornment(currencyCode);

  const settings = usePropertySettings(propertyId);
  // Prefer the settings currency FK, but the seeded/legacy path leaves it null
  // while the real pricing currency lives on the season (its `currency` FK id,
  // passed down as `defaultCurrencyId`). Gate the fallback on settings having
  // resolved so the authoritative FK always wins over the season default when
  // present, regardless of which query resolves first; until then, no fill.
  const defaultCurrency =
    settings.data == null ? null : (settings.data.currency ?? defaultCurrencyId ?? null);

  const form = useForm<ExtraWriteInput>({
    resolver: zodResolver(extraWriteInputSchema),
    defaultValues: isCreate ? createDefaults(defaultCurrency) : defaultsFromExtra(props.entity),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  const createMutation = useCreateExtra(propertyId);
  const updateMutation = useUpdateExtra(propertyId);
  const submitting = createMutation.isPending || updateMutation.isPending;

  useEffect(() => {
    if (!open) return;
    form.reset(isCreate ? createDefaults(defaultCurrency) : defaultsFromExtra(props.entity));
    setTopLevelError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? null : props.entity.id]);

  // The currency default can arrive after the dialog opens (settings load).
  // Fill it in without clobbering the operator's other edits, and only while
  // the field is still unset (0) so a late default never overrides a manual pick.
  useEffect(() => {
    if (open && isCreate && defaultCurrency != null && form.getValues("currency") === 0) {
      form.setValue("currency", defaultCurrency);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, defaultCurrency]);

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

  const kind = form.watch("kind");
  const calc = form.watch("calc");
  const currency = form.watch("currency");
  const currencyMismatch =
    !!currency && !!planCurrencyIds?.length && !planCurrencyIds.includes(currency);
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
              <EnumSelect
                id="extra-kind"
                value={kind}
                onChange={(v) => form.setValue("kind", v, { shouldValidate: true })}
                options={EXTRA_KINDS}
                labelFor={(v) => t(`rate_workbench.inspector.enums.extra_kind.${v}`)}
              />
              {form.formState.errors.kind ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.kind.message)}
                </p>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="extra-calc">{t("rate_workbench.inspector.fields.calc")}</Label>
              <EnumSelect
                id="extra-calc"
                value={calc}
                onChange={(v) => form.setValue("calc", v, { shouldValidate: true })}
                options={EXTRA_CALCS}
                labelFor={(v) => t(`rate_workbench.inspector.enums.extra_calc.${v}`)}
              />
              {form.formState.errors.calc ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.calc.message)}
                </p>
              ) : null}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="extra-amount">{t("rate_workbench.inspector.fields.amount")}</Label>
              <MoneyInput
                id="extra-amount"
                inputMode="decimal"
                adornment={amountAdornment}
                {...form.register("amount")}
              />
              {form.formState.errors.amount ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.amount.message)}
                </p>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="extra-currency">
                {t("rate_workbench.inspector.fields.currency")}
              </Label>
              <CurrencyPicker
                id="extra-currency"
                value={currency || null}
                onChange={(v) => form.setValue("currency", v, { shouldValidate: true })}
                placeholder={t("rate_workbench.inspector.fields.currency_placeholder")}
              />
              {form.formState.errors.currency ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.currency.message)}
                </p>
              ) : null}
            </div>
          </div>

          {currencyMismatch ? (
            <p
              className="border-warning/40 bg-warning/10 text-warning rounded-md border px-3 py-2 text-sm"
              role="note"
            >
              {t("rate_workbench.inspector.extra_dialog.currency_mismatch_hint")}
            </p>
          ) : null}

          <div className="space-y-2">
            <Label htmlFor="extra-description">
              {t("rate_workbench.inspector.fields.description")}
            </Label>
            <Textarea id="extra-description" rows={2} {...form.register("description")} />
          </div>

          {/* Inclusive [applies_from, applies_to] — the extra applies on both
              endpoint days; either side may stay open (empty → null on submit). */}
          <DateRangePicker
            control={form.control}
            fromName="applies_from"
            toName="applies_to"
            mode="days"
            id="extra-dates"
            label={t("rate_workbench.inspector.fields.dates")}
            fromLabel={t("rate_workbench.inspector.fields.applies_from")}
            toLabel={t("rate_workbench.inspector.fields.applies_to")}
            fromError={
              form.formState.errors.applies_from
                ? fieldErrorText(t, form.formState.errors.applies_from.message)
                : undefined
            }
            toError={
              form.formState.errors.applies_to
                ? fieldErrorText(t, form.formState.errors.applies_to.message)
                : undefined
            }
          />

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
