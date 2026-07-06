import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { AdminPageShell } from "@/features/admin/components/AdminPageShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { CheckboxLabel } from "@/components/ui/checkbox-label";
import { MoneyInput } from "@/components/ui/money-input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Section } from "@/components/data/Section";
import { ErrorState } from "@/components/feedback/ErrorState";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { ApiError } from "@/lib/api/errors";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { currencyAdornment } from "@/lib/format/money";
import { formatDateTime } from "@/lib/format/date";
import { useHasAdminRole } from "@/lib/auth/useHasAdminRole";
import { useCurrencies } from "@/features/admin/currencies/hooks";
import {
  PROPERTY_AVAILABILITY_DEFAULTS,
  PROPERTY_CHANGEOVER_DAYS,
  PROPERTY_PRICE_BASES,
} from "@/features/properties/schemas";
import { usePropertyDefaults, useUpdatePropertyDefaults } from "./hooks";
import {
  PROPERTY_DEFAULTS_CALC_TYPES,
  SECURITY_DEPOSIT_PAYMENT_METHODS,
  propertyDefaultsWriteInputSchema,
  type PropertyDefaults,
  type PropertyDefaultsWriteInput,
} from "./schemas";

// Radix Select forbids an empty item value; the blank "—" option for the
// nullable currency FK carries a sentinel the change handler maps to null.
const UNSET_VALUE = "__unset__";

// Every column except `currency` and the two times is non-nullable server-side,
// so the form mirrors the GET payload directly. Times render as "" in the
// <input type="time"> and are mapped back to null on submit when cleared.
function formDefaults(d: PropertyDefaults): PropertyDefaultsWriteInput {
  return {
    availability_default: d.availability_default,
    bookings_require_pre_approval: d.bookings_require_pre_approval,
    requires_enquiry_first: d.requires_enquiry_first,
    currency: d.currency,
    check_in_time: d.check_in_time ?? "",
    check_out_time: d.check_out_time ?? "",
    changeover_day: d.changeover_day,
    min_nights_rental: d.min_nights_rental,
    min_nights_rental_note: d.min_nights_rental_note,
    prices_entered_as: d.prices_entered_as,
    hold_duration_hours: d.hold_duration_hours,
    commission_calculation_type: d.commission_calculation_type,
    commission_amount: d.commission_amount,
    commission_note: d.commission_note,
    tax_is_exempt: d.tax_is_exempt,
    tax_percentage: d.tax_percentage,
    deposit_required: d.deposit_required,
    deposit_calculation_type: d.deposit_calculation_type,
    deposit_amount: d.deposit_amount,
    interim_required: d.interim_required,
    interim_calculation_type: d.interim_calculation_type,
    interim_amount: d.interim_amount,
    days_interim_due_before_arrival: d.days_interim_due_before_arrival,
    days_balance_due_before_arrival: d.days_balance_due_before_arrival,
    security_deposit_required: d.security_deposit_required,
    security_deposit_calculation_type: d.security_deposit_calculation_type,
    security_deposit_amount: d.security_deposit_amount,
    security_deposit_days_due_before_arrival: d.security_deposit_days_due_before_arrival,
    security_deposit_days_refunded_after_departure:
      d.security_deposit_days_refunded_after_departure,
    security_deposit_payment_method: d.security_deposit_payment_method,
    cancellation_fee_amount: d.cancellation_fee_amount,
    cancellation_fee_percent: d.cancellation_fee_percent,
    cancellation_window_days: d.cancellation_window_days,
    cancellation_notes: d.cancellation_notes,
  };
}

const intField = { setValueAs: (v: unknown) => (v === "" || v == null ? null : Number(v)) };

type CalcType = (typeof PROPERTY_DEFAULTS_CALC_TYPES)[number];

function CalcTypeSelect({
  id,
  value,
  onChange,
  disabled,
}: {
  id: string;
  value: CalcType;
  onChange: (value: CalcType) => void;
  disabled: boolean;
}) {
  // Percent/fixed labels are shared with the property SettingsTab, so they come
  // from the properties namespace rather than being duplicated in admin.
  const { t } = useTranslation("properties");
  return (
    <Select value={value} onValueChange={(v) => onChange(v as CalcType)} disabled={disabled}>
      <SelectTrigger id={id}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {PROPERTY_DEFAULTS_CALC_TYPES.map((c) => (
          <SelectItem key={c} value={c}>
            {t(`calc_types.${c}`)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function DefaultsForm({ initial, canWrite }: { initial: PropertyDefaults; canWrite: boolean }) {
  const { t } = useTranslation("admin");
  // Enum labels (availability, changeover days, price bases) already live in
  // the properties namespace — reuse them via a second hook.
  const { t: tProps } = useTranslation("properties");
  const form = useForm<PropertyDefaultsWriteInput>({
    resolver: zodResolver(propertyDefaultsWriteInputSchema),
    defaultValues: formDefaults(initial),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  const mutation = useUpdatePropertyDefaults();
  const currenciesQuery = useCurrencies({});

  useEffect(() => {
    form.reset(formDefaults(initial));
  }, [initial, form]);

  const onSubmit = async (values: PropertyDefaultsWriteInput) => {
    setTopLevelError(null);
    try {
      // Full payload; only the two nullable time fields map "" → null. Note
      // fields pass through untouched so a cleared note submits "" (the
      // columns are non-nullable TextFields).
      await mutation.mutateAsync({
        ...values,
        check_in_time: values.check_in_time ? values.check_in_time : null,
        check_out_time: values.check_out_time ? values.check_out_time : null,
      });
      toast.success(t("property_defaults.saved"));
      form.reset(values);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        setTopLevelError(detail);
      } else {
        toast.error(t("property_defaults.errors.save_failed"));
      }
    }
  };

  const currencies = useMemo(
    () => (currenciesQuery.data?.results ?? []).filter((c) => c.is_active),
    [currenciesQuery.data],
  );
  const currencyId = form.watch("currency");
  const currencyCode = currencies.find((c) => c.id === currencyId)?.code ?? null;
  const amountAdornment = (type: CalcType): string | null =>
    type === "fixed" ? currencyAdornment(currencyCode) : "%";

  const availability = form.watch("availability_default");
  const changeoverDay = form.watch("changeover_day");
  const pricesAs = form.watch("prices_entered_as");
  const commissionType = form.watch("commission_calculation_type");
  const depositType = form.watch("deposit_calculation_type");
  const interimType = form.watch("interim_calculation_type");
  const securityType = form.watch("security_deposit_calculation_type");
  const paymentMethod = form.watch("security_deposit_payment_method");

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} className="max-w-4xl space-y-8" noValidate>
      <Section title={t("property_defaults.sections.operational")}>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="prop-defaults-availability">
              {t("property_defaults.fields.availability_default")}
            </Label>
            <Select
              value={availability}
              onValueChange={(v) =>
                form.setValue(
                  "availability_default",
                  v as PropertyDefaultsWriteInput["availability_default"],
                  { shouldDirty: true },
                )
              }
              disabled={!canWrite}
            >
              <SelectTrigger id="prop-defaults-availability">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PROPERTY_AVAILABILITY_DEFAULTS.map((v) => (
                  <SelectItem key={v} value={v}>
                    {tProps(`availability_defaults.${v}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="prop-defaults-changeover">
              {t("property_defaults.fields.changeover_day")}
            </Label>
            <Select
              value={changeoverDay}
              onValueChange={(v) =>
                form.setValue("changeover_day", v as PropertyDefaultsWriteInput["changeover_day"], {
                  shouldDirty: true,
                })
              }
              disabled={!canWrite}
            >
              <SelectTrigger id="prop-defaults-changeover">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PROPERTY_CHANGEOVER_DAYS.map((d) => (
                  <SelectItem key={d} value={d}>
                    {tProps(`changeover_days.${d}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="prop-defaults-currency">{t("property_defaults.fields.currency")}</Label>
            <Select
              value={currencyId != null ? String(currencyId) : UNSET_VALUE}
              onValueChange={(v) =>
                form.setValue("currency", v === UNSET_VALUE ? null : Number(v), {
                  shouldDirty: true,
                })
              }
              disabled={!canWrite || currenciesQuery.isLoading}
            >
              <SelectTrigger id="prop-defaults-currency">
                <SelectValue placeholder={t("property_defaults.currency_placeholder")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={UNSET_VALUE}>{tProps("common.unset")}</SelectItem>
                {currencies.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>
                    {c.code} — {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="prop-defaults-prices-as">
              {t("property_defaults.fields.prices_entered_as")}
            </Label>
            <Select
              value={pricesAs}
              onValueChange={(v) =>
                form.setValue(
                  "prices_entered_as",
                  v as PropertyDefaultsWriteInput["prices_entered_as"],
                  { shouldDirty: true },
                )
              }
              disabled={!canWrite}
            >
              <SelectTrigger id="prop-defaults-prices-as">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PROPERTY_PRICE_BASES.map((p) => (
                  <SelectItem key={p} value={p}>
                    {tProps(`price_bases.${p}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="prop-defaults-checkin">
              {t("property_defaults.fields.check_in_time")}
            </Label>
            <Input
              id="prop-defaults-checkin"
              type="time"
              disabled={!canWrite}
              {...form.register("check_in_time")}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="prop-defaults-checkout">
              {t("property_defaults.fields.check_out_time")}
            </Label>
            <Input
              id="prop-defaults-checkout"
              type="time"
              disabled={!canWrite}
              {...form.register("check_out_time")}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="prop-defaults-min-nights">
              {t("property_defaults.fields.min_nights_rental")}
            </Label>
            <Input
              id="prop-defaults-min-nights"
              type="number"
              min={0}
              disabled={!canWrite}
              {...form.register("min_nights_rental", intField)}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="prop-defaults-hold-hours">
              {t("property_defaults.fields.hold_duration_hours")}
            </Label>
            <Input
              id="prop-defaults-hold-hours"
              type="number"
              min={0}
              disabled={!canWrite}
              {...form.register("hold_duration_hours", intField)}
            />
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="prop-defaults-min-nights-note">
            {t("property_defaults.fields.min_nights_rental_note")}
          </Label>
          <Textarea
            id="prop-defaults-min-nights-note"
            rows={2}
            disabled={!canWrite}
            {...form.register("min_nights_rental_note")}
          />
        </div>

        <div className="space-y-2">
          <CheckboxLabel>
            <Checkbox
              checked={form.watch("bookings_require_pre_approval")}
              disabled={!canWrite}
              onCheckedChange={(v) =>
                form.setValue("bookings_require_pre_approval", v === true, { shouldDirty: true })
              }
            />
            <span>{t("property_defaults.fields.bookings_require_pre_approval")}</span>
          </CheckboxLabel>
          <CheckboxLabel>
            <Checkbox
              checked={form.watch("requires_enquiry_first")}
              disabled={!canWrite}
              onCheckedChange={(v) =>
                form.setValue("requires_enquiry_first", v === true, { shouldDirty: true })
              }
            />
            <span>{t("property_defaults.fields.requires_enquiry_first")}</span>
          </CheckboxLabel>
        </div>
      </Section>

      <Section title={t("property_defaults.sections.commission_tax")}>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="prop-defaults-commission-type">
              {t("property_defaults.fields.commission_calculation_type")}
            </Label>
            <CalcTypeSelect
              id="prop-defaults-commission-type"
              value={commissionType}
              onChange={(v) =>
                form.setValue("commission_calculation_type", v, { shouldDirty: true })
              }
              disabled={!canWrite}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="prop-defaults-commission-amount">
              {t("property_defaults.fields.commission_amount")}
            </Label>
            <MoneyInput
              id="prop-defaults-commission-amount"
              disabled={!canWrite}
              adornment={amountAdornment(commissionType)}
              {...form.register("commission_amount")}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="prop-defaults-tax-percentage">
              {t("property_defaults.fields.tax_percentage")}
            </Label>
            <Input
              id="prop-defaults-tax-percentage"
              disabled={!canWrite}
              {...form.register("tax_percentage")}
            />
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="prop-defaults-commission-note">
            {t("property_defaults.fields.commission_note")}
          </Label>
          <Textarea
            id="prop-defaults-commission-note"
            rows={2}
            disabled={!canWrite}
            {...form.register("commission_note")}
          />
        </div>

        <CheckboxLabel>
          <Checkbox
            checked={form.watch("tax_is_exempt")}
            disabled={!canWrite}
            onCheckedChange={(v) =>
              form.setValue("tax_is_exempt", v === true, { shouldDirty: true })
            }
          />
          <span>{t("property_defaults.fields.tax_is_exempt")}</span>
        </CheckboxLabel>
      </Section>

      <Section title={t("property_defaults.sections.payment_schedule")}>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="prop-defaults-deposit-type">
              {t("property_defaults.fields.deposit_calculation_type")}
            </Label>
            <CalcTypeSelect
              id="prop-defaults-deposit-type"
              value={depositType}
              onChange={(v) => form.setValue("deposit_calculation_type", v, { shouldDirty: true })}
              disabled={!canWrite}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="prop-defaults-deposit-amount">
              {t("property_defaults.fields.deposit_amount")}
            </Label>
            <MoneyInput
              id="prop-defaults-deposit-amount"
              disabled={!canWrite}
              adornment={amountAdornment(depositType)}
              {...form.register("deposit_amount")}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="prop-defaults-interim-type">
              {t("property_defaults.fields.interim_calculation_type")}
            </Label>
            <CalcTypeSelect
              id="prop-defaults-interim-type"
              value={interimType}
              onChange={(v) => form.setValue("interim_calculation_type", v, { shouldDirty: true })}
              disabled={!canWrite}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="prop-defaults-interim-amount">
              {t("property_defaults.fields.interim_amount")}
            </Label>
            <MoneyInput
              id="prop-defaults-interim-amount"
              disabled={!canWrite}
              adornment={amountAdornment(interimType)}
              {...form.register("interim_amount")}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="prop-defaults-interim-days">
              {t("property_defaults.fields.days_interim_due_before_arrival")}
            </Label>
            <Input
              id="prop-defaults-interim-days"
              type="number"
              min={0}
              disabled={!canWrite}
              {...form.register("days_interim_due_before_arrival", intField)}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="prop-defaults-balance-days">
              {t("property_defaults.fields.days_balance_due_before_arrival")}
            </Label>
            <Input
              id="prop-defaults-balance-days"
              type="number"
              min={0}
              disabled={!canWrite}
              {...form.register("days_balance_due_before_arrival", intField)}
            />
          </div>
        </div>

        <div className="space-y-2">
          <CheckboxLabel>
            <Checkbox
              checked={form.watch("deposit_required")}
              disabled={!canWrite}
              onCheckedChange={(v) =>
                form.setValue("deposit_required", v === true, { shouldDirty: true })
              }
            />
            <span>{t("property_defaults.fields.deposit_required")}</span>
          </CheckboxLabel>
          <CheckboxLabel>
            <Checkbox
              checked={form.watch("interim_required")}
              disabled={!canWrite}
              onCheckedChange={(v) =>
                form.setValue("interim_required", v === true, { shouldDirty: true })
              }
            />
            <span>{t("property_defaults.fields.interim_required")}</span>
          </CheckboxLabel>
        </div>
      </Section>

      <Section title={t("property_defaults.sections.security_deposit")}>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="prop-defaults-security-type">
              {t("property_defaults.fields.security_deposit_calculation_type")}
            </Label>
            <CalcTypeSelect
              id="prop-defaults-security-type"
              value={securityType}
              onChange={(v) =>
                form.setValue("security_deposit_calculation_type", v, { shouldDirty: true })
              }
              disabled={!canWrite}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="prop-defaults-security-amount">
              {t("property_defaults.fields.security_deposit_amount")}
            </Label>
            <MoneyInput
              id="prop-defaults-security-amount"
              disabled={!canWrite}
              adornment={amountAdornment(securityType)}
              {...form.register("security_deposit_amount")}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="prop-defaults-security-method">
              {t("property_defaults.fields.security_deposit_payment_method")}
            </Label>
            <Select
              value={paymentMethod}
              onValueChange={(v) =>
                form.setValue(
                  "security_deposit_payment_method",
                  v as PropertyDefaultsWriteInput["security_deposit_payment_method"],
                  { shouldDirty: true },
                )
              }
              disabled={!canWrite}
            >
              <SelectTrigger id="prop-defaults-security-method">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SECURITY_DEPOSIT_PAYMENT_METHODS.map((m) => (
                  <SelectItem key={m} value={m}>
                    {t(`property_defaults.payment_methods.${m}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="prop-defaults-security-due-days">
              {t("property_defaults.fields.security_deposit_days_due_before_arrival")}
            </Label>
            <Input
              id="prop-defaults-security-due-days"
              type="number"
              min={0}
              disabled={!canWrite}
              {...form.register("security_deposit_days_due_before_arrival", intField)}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="prop-defaults-security-refund-days">
              {t("property_defaults.fields.security_deposit_days_refunded_after_departure")}
            </Label>
            <Input
              id="prop-defaults-security-refund-days"
              type="number"
              min={0}
              disabled={!canWrite}
              {...form.register("security_deposit_days_refunded_after_departure", intField)}
            />
          </div>
        </div>

        <CheckboxLabel>
          <Checkbox
            checked={form.watch("security_deposit_required")}
            disabled={!canWrite}
            onCheckedChange={(v) =>
              form.setValue("security_deposit_required", v === true, { shouldDirty: true })
            }
          />
          <span>{t("property_defaults.fields.security_deposit_required")}</span>
        </CheckboxLabel>
      </Section>

      <Section title={t("property_defaults.sections.cancellation")}>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="prop-defaults-cancellation-amount">
              {t("property_defaults.fields.cancellation_fee_amount")}
            </Label>
            <MoneyInput
              id="prop-defaults-cancellation-amount"
              disabled={!canWrite}
              adornment={currencyAdornment(currencyCode)}
              {...form.register("cancellation_fee_amount")}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="prop-defaults-cancellation-percent">
              {t("property_defaults.fields.cancellation_fee_percent")}
            </Label>
            <Input
              id="prop-defaults-cancellation-percent"
              disabled={!canWrite}
              {...form.register("cancellation_fee_percent")}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="prop-defaults-cancellation-window">
              {t("property_defaults.fields.cancellation_window_days")}
            </Label>
            <Input
              id="prop-defaults-cancellation-window"
              type="number"
              min={0}
              disabled={!canWrite}
              {...form.register("cancellation_window_days", intField)}
            />
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="prop-defaults-cancellation-notes">
            {t("property_defaults.fields.cancellation_notes")}
          </Label>
          <Textarea
            id="prop-defaults-cancellation-notes"
            rows={2}
            disabled={!canWrite}
            {...form.register("cancellation_notes")}
          />
        </div>
      </Section>

      <FormErrorAlert message={topLevelError} fieldErrors={form.formState.errors} />

      <div className="flex justify-end">
        <Button type="submit" disabled={!canWrite || !form.formState.isDirty || mutation.isPending}>
          {mutation.isPending ? t("property_defaults.saving") : t("property_defaults.save")}
        </Button>
      </div>
    </form>
  );
}

export function PropertyDefaultsPage() {
  const { t } = useTranslation("admin");
  const canWrite = useHasAdminRole();
  const query = usePropertyDefaults();

  return (
    <AdminPageShell
      title={t("property_defaults.title")}
      description={t("property_defaults.description")}
    >
      {query.data?.updated_at ? (
        <p className="text-muted-foreground text-sm">
          {t("property_defaults.updated_at_label")}: {formatDateTime(query.data.updated_at)}
        </p>
      ) : null}

      {query.isError ? (
        <ErrorState
          description={t("property_defaults.errors.load_failed")}
          onRetry={() => query.refetch()}
          retrying={query.isFetching}
        />
      ) : query.isLoading || !query.data ? (
        <div className="space-y-2">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      ) : (
        <DefaultsForm initial={query.data} canWrite={canWrite} />
      )}
    </AdminPageShell>
  );
}
