import { useEffect, useRef, useState } from "react";
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
import { addDaysIso, suggestRateBandEnd } from "@/lib/format/date";
import { currencyAdornment, formatMoney } from "@/lib/format/money";
import { deriveNetGross, type CommissionInput, type TaxInput } from "@/lib/pricing/netGross";
import { useCreateRateRule, useUpdateRateRule } from "../hooks";
import {
  rateRuleWriteInputSchema,
  type RateRule,
  type RateRuleWriteInput,
  type RateRuleWritePayload,
} from "../schemas";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";

interface CommonProps {
  seasonId: number;
  cardId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Property changeover settings (GAP-025) for the rate-band end-date
   * suggestion. Both are optional — no fixed changeover means no suggestion. */
  changeoverDay?: string | null;
  minNightsRental?: number | null;
  /** The rate plan's currency code (GAP-026), shown as an adornment beside the
   * nightly/weekly inputs. Null when the season has no currency. */
  currencyCode?: string | null;
  /** GAP-035 net↔gross derivation inputs. `priceBasis` is the season's
   * `price_basis` (what the typed figure represents); `commission`/`tax` are the
   * property's group-resolved effective policy. When all are present the form
   * shows the derived counterpart (owner net for a GROSS plan, guest price for a
   * NET plan) live beside each price input. Absent → no hint, no behaviour change. */
  priceBasis?: string | null;
  commission?: CommissionInput | null;
  tax?: TaxInput | null;
}

interface CreateProps extends CommonProps {
  mode: "create";
  /** Seed values for fast consecutive entry (e.g. date_from = last rule's date_to). */
  defaults?: Partial<RateRuleWriteInput>;
}

interface EditProps extends CommonProps {
  mode: "edit";
  rule: RateRule;
}

type RateRuleFormDialogProps = CreateProps | EditProps;

function createDefaults(seed?: Partial<RateRuleWriteInput>): RateRuleWriteInput {
  return {
    date_from: "",
    date_to: "",
    min_party: 1,
    max_party: 1,
    nightly: "",
    weekly: "",
    is_poa: false,
    notes: "",
    ...seed,
  };
}

function defaultsFromRule(rule: RateRule): RateRuleWriteInput {
  return {
    date_from: rule.date_from,
    date_to: rule.date_to,
    min_party: rule.min_party ?? 1,
    max_party: rule.max_party ?? 1,
    nightly: rule.nightly ?? "",
    weekly: rule.weekly ?? "",
    is_poa: rule.is_poa ?? false,
    notes: rule.notes ?? "",
  };
}

/** Empty or POA-masked prices go to the API as explicit nulls. */
function toPayload(values: RateRuleWriteInput): RateRuleWritePayload {
  return {
    ...values,
    nightly: values.is_poa || !values.nightly ? null : values.nightly,
    weekly: values.is_poa || !values.weekly ? null : values.weekly,
  };
}

/** GAP-035: live net↔gross hint under a price input. Renders the counterpart of
 * the typed figure — owner net for a GROSS plan, guest price for a NET plan —
 * or nothing when the basis/currency is unknown or there's nothing to derive
 * (empty/POA/unpriceable). Display-only; the stored figure is what was typed. */
function DerivedCounterpartHint({
  amount,
  basis,
  commission,
  tax,
  currencyCode,
}: {
  amount: string | undefined;
  basis?: string | null;
  commission?: CommissionInput | null;
  tax?: TaxInput | null;
  currencyCode?: string | null;
}) {
  const { t } = useTranslation("properties");
  if ((basis !== "net" && basis !== "gross") || !currencyCode) return null;
  const derived = deriveNetGross(amount, basis, commission ?? null, tax ?? null);
  if (!derived) return null;
  const label =
    basis === "gross"
      ? t("pricing.rule.dialog.derived.owner_net")
      : t("pricing.rule.dialog.derived.guest_price");
  return (
    <p className="text-muted-foreground text-xs" data-testid="derived-counterpart">
      {label}: {formatMoney(derived.counterpart, currencyCode)}
    </p>
  );
}

export function RateRuleFormDialog(props: RateRuleFormDialogProps) {
  const {
    seasonId,
    cardId,
    open,
    onOpenChange,
    changeoverDay,
    minNightsRental,
    currencyCode,
    priceBasis,
    commission,
    tax,
  } = props;
  const { t } = useTranslation("properties");
  const isCreate = props.mode === "create";
  const priceAdornment = currencyAdornment(currencyCode);

  const form = useForm<RateRuleWriteInput>({
    resolver: zodResolver(rateRuleWriteInputSchema),
    defaultValues: isCreate ? createDefaults(props.defaults) : defaultsFromRule(props.rule),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  const createMutation = useCreateRateRule(seasonId);
  const updateMutation = useUpdateRateRule(seasonId);
  const submitting = createMutation.isPending || updateMutation.isPending;

  useEffect(() => {
    if (open) {
      form.reset(isCreate ? createDefaults(props.defaults) : defaultsFromRule(props.rule));
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? null : props.rule.id]);

  // GAP-025: when the property changes over on a fixed weekday, suggest the
  // band's end date as soon as `date_from` is known — but never clobber a value
  // the user typed (only fill while `date_to` is empty or still holds our own
  // last suggestion). Edit mode keeps the stored value untouched.
  const dateFrom = form.watch("date_from");
  const lastSuggestionRef = useRef<string | null>(null);
  useEffect(() => {
    if (!isCreate || !dateFrom) return;
    const currentTo = form.getValues("date_to");
    if (currentTo && currentTo !== lastSuggestionRef.current) return;
    const suggested = suggestRateBandEnd(dateFrom, changeoverDay, minNightsRental);
    if (!suggested || suggested === currentTo) return;
    lastSuggestionRef.current = suggested;
    form.setValue("date_to", suggested, { shouldDirty: false, shouldValidate: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dateFrom, isCreate, changeoverDay, minNightsRental]);

  const submit = async (values: RateRuleWriteInput, andAddAnother: boolean) => {
    setTopLevelError(null);
    try {
      if (isCreate) {
        await createMutation.mutateAsync({ cardId, input: toPayload(values) });
        toast.success(t("pricing.rule.toasts.created"));
      } else {
        await updateMutation.mutateAsync({ ruleId: props.rule.id, input: toPayload(values) });
        toast.success(t("pricing.rule.toasts.updated"));
      }
      if (andAddAnother) {
        form.reset(
          createDefaults({
            // Rule date ranges are inclusive — the next band starts the day after.
            date_from: addDaysIso(values.date_to, 1),
            min_party: values.min_party,
            max_party: values.max_party,
          }),
        );
        form.setFocus("date_from");
      } else {
        onOpenChange(false);
      }
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        setTopLevelError(detail);
      } else {
        toast.error(
          isCreate
            ? t("pricing.rule.toasts.create_failed")
            : t("pricing.rule.toasts.update_failed"),
        );
      }
    }
  };

  const isPoa = form.watch("is_poa");
  const nightly = form.watch("nightly");
  const weekly = form.watch("weekly");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isCreate ? t("pricing.rule.dialog.create_title") : t("pricing.rule.dialog.edit_title")}
          </DialogTitle>
        </DialogHeader>
        <form
          onSubmit={form.handleSubmit((values) => submit(values, false))}
          className="space-y-4"
          noValidate
        >
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="rate-rule-date-from">
                {t("pricing.rule.dialog.fields.date_from")}
              </Label>
              <Input id="rate-rule-date-from" type="date" {...form.register("date_from")} />
              {form.formState.errors.date_from ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.date_from.message)}
                </p>
              ) : null}
            </div>

            <div className="space-y-2">
              <Label htmlFor="rate-rule-date-to">{t("pricing.rule.dialog.fields.date_to")}</Label>
              <Input id="rate-rule-date-to" type="date" {...form.register("date_to")} />
              {form.formState.errors.date_to ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.date_to.message)}
                </p>
              ) : null}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="rate-rule-min-party">
                {t("pricing.rule.dialog.fields.min_party")}
              </Label>
              <Input
                id="rate-rule-min-party"
                type="number"
                min={1}
                {...form.register("min_party", {
                  setValueAs: (v) => (v === "" || v == null ? undefined : Number(v)),
                })}
              />
              {form.formState.errors.min_party ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.min_party.message)}
                </p>
              ) : null}
            </div>

            <div className="space-y-2">
              <Label htmlFor="rate-rule-max-party">
                {t("pricing.rule.dialog.fields.max_party")}
              </Label>
              <Input
                id="rate-rule-max-party"
                type="number"
                min={1}
                {...form.register("max_party", {
                  setValueAs: (v) => (v === "" || v == null ? undefined : Number(v)),
                })}
              />
              {form.formState.errors.max_party ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.max_party.message)}
                </p>
              ) : null}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Checkbox
              id="rate-rule-is-poa"
              checked={isPoa}
              onCheckedChange={(v) => {
                form.setValue("is_poa", v === true);
                // Price errors no longer apply once POA masks the inputs.
                form.clearErrors(["nightly", "weekly"]);
              }}
            />
            <Label htmlFor="rate-rule-is-poa">{t("pricing.rule.dialog.fields.is_poa")}</Label>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="rate-rule-nightly">{t("pricing.rule.dialog.fields.nightly")}</Label>
              <MoneyInput
                id="rate-rule-nightly"
                inputMode="decimal"
                disabled={isPoa}
                adornment={isPoa ? null : priceAdornment}
                {...form.register("nightly")}
              />
              {form.formState.errors.nightly ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.nightly.message)}
                </p>
              ) : null}
              {!isPoa ? (
                <DerivedCounterpartHint
                  amount={nightly}
                  basis={priceBasis}
                  commission={commission}
                  tax={tax}
                  currencyCode={currencyCode}
                />
              ) : null}
            </div>

            <div className="space-y-2">
              <Label htmlFor="rate-rule-weekly">{t("pricing.rule.dialog.fields.weekly")}</Label>
              <MoneyInput
                id="rate-rule-weekly"
                inputMode="decimal"
                disabled={isPoa}
                adornment={isPoa ? null : priceAdornment}
                {...form.register("weekly")}
              />
              {form.formState.errors.weekly ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.weekly.message)}
                </p>
              ) : null}
              {!isPoa ? (
                <DerivedCounterpartHint
                  amount={weekly}
                  basis={priceBasis}
                  commission={commission}
                  tax={tax}
                  currencyCode={currencyCode}
                />
              ) : null}
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="rate-rule-notes">{t("pricing.rule.dialog.fields.notes")}</Label>
            <Textarea id="rate-rule-notes" rows={2} {...form.register("notes")} />
          </div>

          <FormErrorAlert message={topLevelError} />

          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              {t("pricing.rule.dialog.actions.cancel")}
            </Button>
            {isCreate ? (
              <Button
                type="button"
                variant="secondary"
                disabled={submitting}
                onClick={form.handleSubmit((values) => submit(values, true))}
              >
                {t("pricing.rule.dialog.actions.save_and_add")}
              </Button>
            ) : null}
            <Button type="submit" disabled={submitting}>
              {submitting
                ? t("pricing.rule.dialog.actions.saving")
                : t("pricing.rule.dialog.actions.save")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
