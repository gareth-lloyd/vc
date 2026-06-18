import { useEffect, useMemo, useState } from "react";
import { CheckboxLabel } from "@/components/ui/checkbox-label";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { useOutletContext } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MoneyInput } from "@/components/ui/money-input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Section } from "@/components/data/Section";
import { ErrorState } from "@/components/feedback/ErrorState";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { ChangeoverRulesSection } from "../components/ChangeoverRulesSection";
import { ApiError } from "@/lib/api/errors";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { currencyAdornment } from "@/lib/format/money";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import {
  useActivateProperty,
  useArchiveProperty,
  usePropertyFinance,
  usePropertyLocation,
  usePropertySettings,
  useRestoreProperty,
  useUpdatePropertyFinance,
  useUpdatePropertyLocation,
  useUpdatePropertySettings,
} from "../hooks";
import { CountryPicker } from "../components/CountryPicker";
import {
  PROPERTY_AVAILABILITY_DEFAULTS,
  PROPERTY_CHANGEOVER_DAYS,
  PROPERTY_PRICE_BASES,
  propertyFinanceWriteInputSchema,
  propertyLocationWriteInputSchema,
  propertySettingsWriteInputSchema,
  type PropertyDetail,
  type PropertyFinance,
  type PropertyFinanceWriteInput,
  type PropertyLocation,
  type PropertyLocationWriteInput,
  type PropertySettings,
  type PropertySettingsWriteInput,
} from "../schemas";

interface SettingsContext {
  property: PropertyDetail;
}

const INHERIT_VALUE = "__inherit__";
const CALC_TYPES = ["percent", "fixed"] as const;

// IANA zones straight from the runtime; the backend validates against zoneinfo.
const TIMEZONE_OPTIONS: readonly string[] =
  typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [];

function settingsDefaults(s: PropertySettings): PropertySettingsWriteInput {
  return {
    availability_default: s.availability_default ?? null,
    bookings_require_pre_approval: s.bookings_require_pre_approval ?? null,
    requires_enquiry_first: s.requires_enquiry_first ?? null,
    check_in_time: s.check_in_time ?? "",
    check_out_time: s.check_out_time ?? "",
    changeover_day: s.changeover_day ?? null,
    min_nights_rental: s.min_nights_rental ?? null,
    min_nights_rental_note: s.min_nights_rental_note ?? "",
    prices_entered_as: s.prices_entered_as ?? null,
  };
}

function financeDefaults(f: PropertyFinance): PropertyFinanceWriteInput {
  return {
    commission_calculation_type: f.commission_calculation_type ?? null,
    commission_amount: f.commission_amount ?? "",
    commission_note: f.commission_note ?? "",
    tax_number: f.tax_number ?? "",
    tax_is_exempt: f.tax_is_exempt ?? false,
    tax_percentage: f.tax_percentage ?? "",
    deposit_required: f.deposit_required ?? false,
    deposit_calculation_type: f.deposit_calculation_type ?? null,
    deposit_amount: f.deposit_amount ?? "",
    days_balance_due_before_arrival: f.days_balance_due_before_arrival ?? null,
    security_deposit_required: f.security_deposit_required ?? false,
    security_deposit_calculation_type: f.security_deposit_calculation_type ?? null,
    security_deposit_amount: f.security_deposit_amount ?? "",
    cancellation_fee_percent: f.cancellation_fee_percent ?? "",
    cancellation_window_days: f.cancellation_window_days ?? null,
    notes: f.notes ?? "",
  };
}

function locationDefaults(l: PropertyLocation): PropertyLocationWriteInput {
  return {
    address_line_1: l.address_line_1 ?? "",
    address_line_2: l.address_line_2 ?? "",
    address_line_3: l.address_line_3 ?? "",
    post_code: l.post_code ?? "",
    locality_town: l.locality_town ?? "",
    locality_region: l.locality_region ?? "",
    country: l.country,
    latitude: l.latitude ?? "",
    longitude: l.longitude ?? "",
    timezone: l.timezone,
  };
}

function blankToNull<T extends Record<string, unknown>>(values: T): T {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(values)) {
    out[k] = v === "" ? null : v;
  }
  return out as T;
}

function OperationalForm({
  propertyId,
  initial,
  canWrite,
}: {
  propertyId: number;
  initial: PropertySettings;
  canWrite: boolean;
}) {
  const { t } = useTranslation("properties");
  const form = useForm<PropertySettingsWriteInput>({
    resolver: zodResolver(propertySettingsWriteInputSchema),
    defaultValues: settingsDefaults(initial),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  const mutation = useUpdatePropertySettings(propertyId);

  useEffect(() => {
    form.reset(settingsDefaults(initial));
  }, [initial, form]);

  const onSubmit = async (values: PropertySettingsWriteInput) => {
    setTopLevelError(null);
    try {
      await mutation.mutateAsync(blankToNull(values));
      toast.success(t("settings.operational.saved"));
      form.reset(values);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        setTopLevelError(detail);
      } else {
        toast.error(t("settings.operational.save_failed"));
      }
    }
  };

  const availability = form.watch("availability_default") ?? null;
  const changeoverDay = form.watch("changeover_day") ?? null;
  const pricesAs = form.watch("prices_entered_as") ?? null;
  const preApproval = form.watch("bookings_require_pre_approval");
  const enquiryFirst = form.watch("requires_enquiry_first");

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
      <p className="text-muted-foreground text-sm">{t("settings.operational.description")}</p>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="prop-settings-availability">
            {t("settings.operational.fields.availability_default")}
          </Label>
          <Select
            value={availability ?? INHERIT_VALUE}
            onValueChange={(v) =>
              form.setValue("availability_default", v === INHERIT_VALUE ? null : v, {
                shouldDirty: true,
              })
            }
            disabled={!canWrite}
          >
            <SelectTrigger id="prop-settings-availability">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={INHERIT_VALUE}>{t("common.inherit")}</SelectItem>
              {PROPERTY_AVAILABILITY_DEFAULTS.map((v) => (
                <SelectItem key={v} value={v}>
                  {t(`availability_defaults.${v}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="prop-settings-changeover">
            {t("settings.operational.fields.changeover_day")}
          </Label>
          <Select
            value={changeoverDay ?? INHERIT_VALUE}
            onValueChange={(v) =>
              form.setValue("changeover_day", v === INHERIT_VALUE ? null : v, {
                shouldDirty: true,
              })
            }
            disabled={!canWrite}
          >
            <SelectTrigger id="prop-settings-changeover">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={INHERIT_VALUE}>{t("common.inherit")}</SelectItem>
              {PROPERTY_CHANGEOVER_DAYS.map((d) => (
                <SelectItem key={d} value={d}>
                  {t(`changeover_days.${d}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="prop-settings-checkin">
            {t("settings.operational.fields.check_in_time")}
          </Label>
          <Input
            id="prop-settings-checkin"
            type="time"
            disabled={!canWrite}
            {...form.register("check_in_time")}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="prop-settings-checkout">
            {t("settings.operational.fields.check_out_time")}
          </Label>
          <Input
            id="prop-settings-checkout"
            type="time"
            disabled={!canWrite}
            {...form.register("check_out_time")}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="prop-settings-min-nights">
            {t("settings.operational.fields.min_nights_rental")}
          </Label>
          <Input
            id="prop-settings-min-nights"
            type="number"
            min={0}
            disabled={!canWrite}
            {...form.register("min_nights_rental", {
              setValueAs: (v) => (v === "" || v == null ? null : Number(v)),
            })}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="prop-settings-prices-as">
            {t("settings.operational.fields.prices_entered_as")}
          </Label>
          <Select
            value={pricesAs ?? INHERIT_VALUE}
            onValueChange={(v) =>
              form.setValue("prices_entered_as", v === INHERIT_VALUE ? null : v, {
                shouldDirty: true,
              })
            }
            disabled={!canWrite}
          >
            <SelectTrigger id="prop-settings-prices-as">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={INHERIT_VALUE}>{t("common.inherit")}</SelectItem>
              {PROPERTY_PRICE_BASES.map((p) => (
                <SelectItem key={p} value={p}>
                  {t(`price_bases.${p}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="prop-settings-min-nights-note">
          {t("settings.operational.fields.min_nights_rental_note")}
        </Label>
        <Textarea
          id="prop-settings-min-nights-note"
          rows={2}
          disabled={!canWrite}
          {...form.register("min_nights_rental_note")}
        />
      </div>

      <div className="space-y-2">
        <CheckboxLabel>
          <Checkbox
            checked={preApproval === true}
            disabled={!canWrite}
            onCheckedChange={(v) =>
              form.setValue("bookings_require_pre_approval", v === true, { shouldDirty: true })
            }
          />
          <span>{t("settings.operational.fields.bookings_require_pre_approval")}</span>
        </CheckboxLabel>
        <CheckboxLabel>
          <Checkbox
            checked={enquiryFirst === true}
            disabled={!canWrite}
            onCheckedChange={(v) =>
              form.setValue("requires_enquiry_first", v === true, { shouldDirty: true })
            }
          />
          <span>{t("settings.operational.fields.requires_enquiry_first")}</span>
        </CheckboxLabel>
      </div>

      <FormErrorAlert message={topLevelError} fieldErrors={form.formState.errors} />

      <div className="flex justify-end">
        <Button type="submit" disabled={!canWrite || !form.formState.isDirty || mutation.isPending}>
          {mutation.isPending ? t("settings.operational.saving") : t("settings.operational.save")}
        </Button>
      </div>
    </form>
  );
}

function FinanceForm({
  propertyId,
  initial,
  canWrite,
}: {
  propertyId: number;
  initial: PropertyFinance;
  canWrite: boolean;
}) {
  const { t } = useTranslation("properties");
  const form = useForm<PropertyFinanceWriteInput>({
    resolver: zodResolver(propertyFinanceWriteInputSchema),
    defaultValues: financeDefaults(initial),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  const mutation = useUpdatePropertyFinance(propertyId);

  useEffect(() => {
    form.reset(financeDefaults(initial));
  }, [initial, form]);

  const onSubmit = async (values: PropertyFinanceWriteInput) => {
    setTopLevelError(null);
    try {
      await mutation.mutateAsync(blankToNull(values));
      toast.success(t("settings.finance.saved"));
      form.reset(values);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        setTopLevelError(detail);
      } else {
        toast.error(t("settings.finance.save_failed"));
      }
    }
  };

  const commissionType = form.watch("commission_calculation_type") ?? null;
  const depositType = form.watch("deposit_calculation_type") ?? null;
  const securityType = form.watch("security_deposit_calculation_type") ?? null;

  // GAP-026: adorn each amount with the unit it's denominated in — the
  // property's effective currency for a `fixed` amount, "%" for a `percent`
  // one. An inherited (null) type resolves its basis from the group, which the
  // client can't see here, so it stays unadorned rather than guess.
  const settings = usePropertySettings(propertyId);
  const currencyCode = settings.data?.currency_code ?? null;
  const amountAdornment = (type: string | null): string | null =>
    type === "fixed" ? currencyAdornment(currencyCode) : type === "percent" ? "%" : null;
  // Prompt to set a currency only when a `fixed` amount is actually in play but
  // no currency resolves — otherwise the amount renders with a blank prefix.
  const showNoCurrencyPrompt =
    !!settings.data &&
    !currencyCode &&
    [commissionType, depositType, securityType].includes("fixed");

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
      <p className="text-muted-foreground text-sm">{t("settings.finance.description")}</p>
      {showNoCurrencyPrompt ? (
        <p
          role="status"
          className="border-warning/40 bg-warning/10 text-warning rounded-md border px-3 py-2 text-sm"
        >
          {t("settings.finance.no_currency_prompt")}
        </p>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="prop-finance-commission-type">
            {t("settings.finance.fields.commission_calculation_type")}
          </Label>
          <Select
            value={commissionType ?? INHERIT_VALUE}
            onValueChange={(v) =>
              form.setValue("commission_calculation_type", v === INHERIT_VALUE ? null : v, {
                shouldDirty: true,
              })
            }
            disabled={!canWrite}
          >
            <SelectTrigger id="prop-finance-commission-type">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={INHERIT_VALUE}>{t("common.inherit")}</SelectItem>
              {CALC_TYPES.map((c) => (
                <SelectItem key={c} value={c}>
                  {t(`calc_types.${c}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="prop-finance-commission-amount">
            {t("settings.finance.fields.commission_amount")}
          </Label>
          <MoneyInput
            id="prop-finance-commission-amount"
            disabled={!canWrite}
            adornment={amountAdornment(commissionType)}
            {...form.register("commission_amount")}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="prop-finance-tax-number">{t("settings.finance.fields.tax_number")}</Label>
          <Input
            id="prop-finance-tax-number"
            disabled={!canWrite}
            {...form.register("tax_number")}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="prop-finance-tax-percent">
            {t("settings.finance.fields.tax_percentage")}
          </Label>
          <Input
            id="prop-finance-tax-percent"
            disabled={!canWrite}
            {...form.register("tax_percentage")}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="prop-finance-deposit-type">
            {t("settings.finance.fields.deposit_calculation_type")}
          </Label>
          <Select
            value={depositType ?? INHERIT_VALUE}
            onValueChange={(v) =>
              form.setValue("deposit_calculation_type", v === INHERIT_VALUE ? null : v, {
                shouldDirty: true,
              })
            }
            disabled={!canWrite}
          >
            <SelectTrigger id="prop-finance-deposit-type">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={INHERIT_VALUE}>{t("common.inherit")}</SelectItem>
              {CALC_TYPES.map((c) => (
                <SelectItem key={c} value={c}>
                  {t(`calc_types.${c}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="prop-finance-deposit-amount">
            {t("settings.finance.fields.deposit_amount")}
          </Label>
          <MoneyInput
            id="prop-finance-deposit-amount"
            disabled={!canWrite}
            adornment={amountAdornment(depositType)}
            {...form.register("deposit_amount")}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="prop-finance-balance-days">
            {t("settings.finance.fields.days_balance_due_before_arrival")}
          </Label>
          <Input
            id="prop-finance-balance-days"
            type="number"
            min={0}
            disabled={!canWrite}
            {...form.register("days_balance_due_before_arrival", {
              setValueAs: (v) => (v === "" || v == null ? null : Number(v)),
            })}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="prop-finance-security-type">
            {t("settings.finance.fields.security_deposit_calculation_type")}
          </Label>
          <Select
            value={securityType ?? INHERIT_VALUE}
            onValueChange={(v) =>
              form.setValue("security_deposit_calculation_type", v === INHERIT_VALUE ? null : v, {
                shouldDirty: true,
              })
            }
            disabled={!canWrite}
          >
            <SelectTrigger id="prop-finance-security-type">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={INHERIT_VALUE}>{t("common.inherit")}</SelectItem>
              {CALC_TYPES.map((c) => (
                <SelectItem key={c} value={c}>
                  {t(`calc_types.${c}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="prop-finance-security-amount">
            {t("settings.finance.fields.security_deposit_amount")}
          </Label>
          <MoneyInput
            id="prop-finance-security-amount"
            disabled={!canWrite}
            adornment={amountAdornment(securityType)}
            {...form.register("security_deposit_amount")}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="prop-finance-cancellation-percent">
            {t("settings.finance.fields.cancellation_fee_percent")}
          </Label>
          <Input
            id="prop-finance-cancellation-percent"
            disabled={!canWrite}
            {...form.register("cancellation_fee_percent")}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="prop-finance-cancellation-window">
            {t("settings.finance.fields.cancellation_window_days")}
          </Label>
          <Input
            id="prop-finance-cancellation-window"
            type="number"
            min={0}
            disabled={!canWrite}
            {...form.register("cancellation_window_days", {
              setValueAs: (v) => (v === "" || v == null ? null : Number(v)),
            })}
          />
        </div>
      </div>

      <div className="space-y-2">
        <CheckboxLabel>
          <Checkbox
            checked={form.watch("deposit_required") === true}
            disabled={!canWrite}
            onCheckedChange={(v) =>
              form.setValue("deposit_required", v === true, { shouldDirty: true })
            }
          />
          <span>{t("settings.finance.fields.deposit_required")}</span>
        </CheckboxLabel>
        <CheckboxLabel>
          <Checkbox
            checked={form.watch("security_deposit_required") === true}
            disabled={!canWrite}
            onCheckedChange={(v) =>
              form.setValue("security_deposit_required", v === true, { shouldDirty: true })
            }
          />
          <span>{t("settings.finance.fields.security_deposit_required")}</span>
        </CheckboxLabel>
        <CheckboxLabel>
          <Checkbox
            checked={form.watch("tax_is_exempt") === true}
            disabled={!canWrite}
            onCheckedChange={(v) =>
              form.setValue("tax_is_exempt", v === true, { shouldDirty: true })
            }
          />
          <span>{t("settings.finance.fields.tax_is_exempt")}</span>
        </CheckboxLabel>
      </div>

      <div className="space-y-2">
        <Label htmlFor="prop-finance-notes">{t("settings.finance.fields.notes")}</Label>
        <Textarea
          id="prop-finance-notes"
          rows={3}
          disabled={!canWrite}
          {...form.register("notes")}
        />
      </div>

      <FormErrorAlert message={topLevelError} fieldErrors={form.formState.errors} />

      <div className="flex justify-end">
        <Button type="submit" disabled={!canWrite || !form.formState.isDirty || mutation.isPending}>
          {mutation.isPending ? t("settings.finance.saving") : t("settings.finance.save")}
        </Button>
      </div>
    </form>
  );
}

function LocationForm({
  propertyId,
  initial,
  canWrite,
}: {
  propertyId: number;
  initial: PropertyLocation;
  canWrite: boolean;
}) {
  const { t } = useTranslation("properties");
  const form = useForm<PropertyLocationWriteInput>({
    resolver: zodResolver(propertyLocationWriteInputSchema),
    defaultValues: locationDefaults(initial),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  const mutation = useUpdatePropertyLocation(propertyId);

  useEffect(() => {
    form.reset(locationDefaults(initial));
  }, [initial, form]);

  const onSubmit = async (values: PropertyLocationWriteInput) => {
    setTopLevelError(null);
    try {
      // Address/locality are non-null CharFields (blank ""), but lat/lng are
      // nullable — clear them with null rather than an empty string.
      await mutation.mutateAsync({
        ...values,
        latitude: values.latitude ? values.latitude : null,
        longitude: values.longitude ? values.longitude : null,
      });
      toast.success(t("settings.location.saved"));
      form.reset(values);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        setTopLevelError(detail);
      } else {
        toast.error(t("settings.location.save_failed"));
      }
    }
  };

  const country = form.watch("country");
  const timezone = form.watch("timezone") ?? "";
  // Keep an admin-set zone outside the runtime list selectable/visible. Memoised
  // so the ~400-entry list isn't rebuilt on every keystroke.
  const timezoneOptions = useMemo(
    () =>
      timezone && !TIMEZONE_OPTIONS.includes(timezone)
        ? [timezone, ...TIMEZONE_OPTIONS]
        : TIMEZONE_OPTIONS,
    [timezone],
  );

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
      <p className="text-muted-foreground text-sm">{t("settings.location.description")}</p>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="prop-location-address-1">
            {t("settings.location.fields.address_line_1")}
          </Label>
          <Input
            id="prop-location-address-1"
            disabled={!canWrite}
            {...form.register("address_line_1")}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="prop-location-address-2">
            {t("settings.location.fields.address_line_2")}
          </Label>
          <Input
            id="prop-location-address-2"
            disabled={!canWrite}
            {...form.register("address_line_2")}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="prop-location-address-3">
            {t("settings.location.fields.address_line_3")}
          </Label>
          <Input
            id="prop-location-address-3"
            disabled={!canWrite}
            {...form.register("address_line_3")}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="prop-location-post-code">{t("settings.location.fields.post_code")}</Label>
          <Input
            id="prop-location-post-code"
            disabled={!canWrite}
            {...form.register("post_code")}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="prop-location-town">{t("settings.location.fields.locality_town")}</Label>
          <Input id="prop-location-town" disabled={!canWrite} {...form.register("locality_town")} />
        </div>

        <div className="space-y-2">
          <Label htmlFor="prop-location-region">
            {t("settings.location.fields.locality_region")}
          </Label>
          <Input
            id="prop-location-region"
            disabled={!canWrite}
            {...form.register("locality_region")}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="prop-location-country">{t("settings.location.fields.country")}</Label>
          <CountryPicker
            id="prop-location-country"
            value={country}
            onChange={(v) => form.setValue("country", v, { shouldDirty: true })}
            placeholder={t("settings.location.country_placeholder")}
            disabled={!canWrite}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="prop-location-timezone">{t("settings.location.fields.timezone")}</Label>
          <Select
            value={timezone}
            onValueChange={(v) => form.setValue("timezone", v, { shouldDirty: true })}
            disabled={!canWrite}
          >
            <SelectTrigger id="prop-location-timezone">
              <SelectValue placeholder={t("settings.location.timezone_placeholder")} />
            </SelectTrigger>
            <SelectContent>
              {timezoneOptions.map((z) => (
                <SelectItem key={z} value={z}>
                  {z}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="prop-location-latitude">{t("settings.location.fields.latitude")}</Label>
          <Input id="prop-location-latitude" disabled={!canWrite} {...form.register("latitude")} />
        </div>

        <div className="space-y-2">
          <Label htmlFor="prop-location-longitude">{t("settings.location.fields.longitude")}</Label>
          <Input
            id="prop-location-longitude"
            disabled={!canWrite}
            {...form.register("longitude")}
          />
        </div>
      </div>

      <FormErrorAlert message={topLevelError} />

      <div className="flex justify-end">
        <Button type="submit" disabled={!canWrite || !form.formState.isDirty || mutation.isPending}>
          {mutation.isPending ? t("settings.location.saving") : t("settings.location.save")}
        </Button>
      </div>
    </form>
  );
}

type LifecycleAction = "activate" | "archive" | "restore";

function LifecycleActions({ property, canWrite }: { property: PropertyDetail; canWrite: boolean }) {
  const { t } = useTranslation("properties");
  const [pending, setPending] = useState<LifecycleAction | null>(null);
  const activate = useActivateProperty(property);
  const archive = useArchiveProperty(property);
  const restore = useRestoreProperty(property);

  const handleConfirm = async () => {
    if (!pending) return;
    try {
      if (pending === "activate") {
        await activate.mutateAsync();
        toast.success(t("settings.lifecycle.toasts.activated"));
      } else if (pending === "archive") {
        await archive.mutateAsync();
        toast.success(t("settings.lifecycle.toasts.archived"));
      } else if (pending === "restore") {
        await restore.mutateAsync();
        toast.success(t("settings.lifecycle.toasts.restored"));
      }
      setPending(null);
    } catch (error) {
      if (error instanceof ApiError) {
        toast.error(error.detail);
      } else {
        toast.error(t("settings.lifecycle.toasts.failed"));
      }
    }
  };

  const status = property.status;
  const showActivate = status === "draft";
  const showArchive = status === "active";
  const showRestore = status === "archived";

  const button = (action: LifecycleAction, label: string, variant: "default" | "destructive") =>
    canWrite ? (
      <Button variant={variant} size="sm" onClick={() => setPending(action)}>
        {label}
      </Button>
    ) : (
      <Tooltip>
        <TooltipTrigger asChild>
          <span>
            <Button variant={variant} size="sm" disabled>
              {label}
            </Button>
          </span>
        </TooltipTrigger>
        <TooltipContent>{t("settings.lifecycle.role_required")}</TooltipContent>
      </Tooltip>
    );

  const confirmTitle = pending ? t(`settings.lifecycle.confirm.${pending}_title`) : "";
  const confirmDescription = pending ? t(`settings.lifecycle.confirm.${pending}_description`) : "";
  const busy = activate.isPending || archive.isPending || restore.isPending;

  return (
    <div className="space-y-3">
      <p className="text-muted-foreground text-sm">{t("settings.lifecycle.description")}</p>
      <p className="text-sm">
        <span className="text-muted-foreground">{t("settings.lifecycle.current_status")}: </span>
        <span className="font-medium capitalize">{status}</span>
      </p>
      <div className="flex flex-wrap gap-2">
        {showActivate
          ? button("activate", t("settings.lifecycle.actions.activate"), "default")
          : null}
        {showArchive
          ? button("archive", t("settings.lifecycle.actions.archive"), "destructive")
          : null}
        {showRestore ? button("restore", t("settings.lifecycle.actions.restore"), "default") : null}
      </div>

      {pending ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setPending(null)}
          onConfirm={handleConfirm}
          title={confirmTitle}
          description={confirmDescription}
          destructive={pending === "archive"}
          busy={busy}
        />
      ) : null}
    </div>
  );
}

export function SettingsTab() {
  const { property } = useOutletContext<SettingsContext>();
  const { t } = useTranslation("properties");
  const canWrite = useHasReservationsRole();
  const settings = usePropertySettings(property.id);
  const finance = usePropertyFinance(property.id);
  const location = usePropertyLocation(property.id);

  if (settings.isLoading || finance.isLoading || location.isLoading) {
    return (
      <div className="space-y-6 p-6">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (
    settings.isError ||
    finance.isError ||
    location.isError ||
    !settings.data ||
    !finance.data ||
    !location.data
  ) {
    return (
      <div className="p-6">
        <ErrorState
          description={t("settings.errors.load_failed")}
          onRetry={() => {
            settings.refetch();
            finance.refetch();
            location.refetch();
          }}
          retrying={settings.isFetching || finance.isFetching || location.isFetching}
        />
      </div>
    );
  }

  return (
    <div className="space-y-8 p-6">
      <h2 className="text-lg font-semibold">{t("settings.title")}</h2>

      <Section title={t("settings.operational.title")}>
        <OperationalForm propertyId={property.id} initial={settings.data} canWrite={canWrite} />
      </Section>

      <Section title={t("settings.location.title")}>
        <LocationForm propertyId={property.id} initial={location.data} canWrite={canWrite} />
      </Section>

      <Section title={t("settings.finance.title")}>
        <FinanceForm propertyId={property.id} initial={finance.data} canWrite={canWrite} />
      </Section>

      <Section title={t("changeover.section_title")}>
        <ChangeoverRulesSection propertyId={property.id} />
      </Section>

      <Section title={t("settings.lifecycle.title")}>
        <LifecycleActions property={property} canWrite={canWrite} />
      </Section>
    </div>
  );
}
