import { useEffect, useState, type ChangeEvent } from "react";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/errors";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { fieldErrorText } from "@/lib/forms/fieldError";
import { todayIso } from "@/lib/format/date";
import { currencyAdornment, formatMoney } from "@/lib/format/money";
import {
  deriveNetGross,
  roundHalfEven,
  type CommissionInput,
  type TaxInput,
} from "@/lib/pricing/netGross";
import { useCreateRateBand, useUpdateRateBand } from "../hooks";
import {
  MONEY_PATTERN,
  PERCENT_PATTERN,
  rateBandWriteInputSchema,
  type RateBand,
  type RateBandWriteInput,
  type RateBandWritePayload,
} from "../schemas";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";

interface CommonProps {
  ratePlanId: number;
  /** The parent period this band belongs to (GAP-056 — dates live on it). */
  periodId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The rate plan's currency code (GAP-026), shown as an adornment beside the
   * nightly/weekly inputs. Null when the season has no currency. */
  currencyCode?: string | null;
  /** GAP-035 net↔gross derivation inputs. `priceBasis` is the season's
   * `price_basis` (what the typed figure represents); `commission`/`tax` are the
   * property's effective policy. When all are present the form
   * shows the derived counterpart (owner net for a GROSS plan, guest price for a
   * NET plan) live beside each price input. Absent → no hint, no behaviour change. */
  priceBasis?: string | null;
  commission?: CommissionInput | null;
  tax?: TaxInput | null;
  /** The owning plan's pricing mode. When `false` (flat rate) party size is
   * ignored: the min/max party inputs are hidden and the single band is auto-set
   * to cover the whole party range (1..capacity). Defaults to occupancy. */
  pricesByOccupancy?: boolean;
  /** The property's guest capacity — the `max_party` a flat band spans, so a
   * booking of any party size prices (the engine still matches party against the
   * band range even for flat plans). Null falls back to 1. */
  capacity?: number | null;
}

interface CreateProps extends CommonProps {
  mode: "create";
  /** Seed values for fast consecutive entry (e.g. next party band = last max_party + 1). */
  defaults?: Partial<RateBandWriteInput>;
}

interface EditProps extends CommonProps {
  mode: "edit";
  rule: RateBand;
}

type RateBandFormDialogProps = CreateProps | EditProps;

function createDefaults(seed?: Partial<RateBandWriteInput>): RateBandWriteInput {
  return {
    min_party: 1,
    max_party: 1,
    nightly: "",
    weekly: "",
    is_poa: false,
    notes: "",
    reduction_percent: "",
    reduced_nightly: "",
    reduced_weekly: "",
    reduced_at: "",
    reduction_reason: "",
    ...seed,
  };
}

function defaultsFromRule(rule: RateBand): RateBandWriteInput {
  return {
    min_party: rule.min_party ?? 1,
    max_party: rule.max_party ?? 1,
    nightly: rule.nightly ?? "",
    weekly: rule.weekly ?? "",
    is_poa: rule.is_poa ?? false,
    notes: rule.notes ?? "",
    reduction_percent: rule.reduction_percent ?? "",
    reduced_nightly: rule.reduced_nightly ?? "",
    reduced_weekly: rule.reduced_weekly ?? "",
    reduced_at: rule.reduced_at ?? "",
    reduction_reason: rule.reduction_reason ?? "",
  };
}

/** Q-018: which reduction editor the form values call for. */
type ReductionKind = "none" | "percent" | "fixed";

const REDUCTION_FIELDS = [
  "reduction_percent",
  "reduced_nightly",
  "reduced_weekly",
  "reduced_at",
  "reduction_reason",
] as const;

function reductionKindOf(values: RateBandWriteInput): ReductionKind {
  if (values.reduction_percent) return "percent";
  if (values.reduced_nightly || values.reduced_weekly) return "fixed";
  return "none";
}

/** Empty or POA-masked prices go to the API as explicit nulls. */
function toPayload(values: RateBandWriteInput): RateBandWritePayload {
  // Q-018: cleared (or POA-masked) reduction values go as explicit nulls so
  // the server wipes the stored reduction.
  const reduction_percent =
    values.is_poa || !values.reduction_percent ? null : values.reduction_percent;
  const reduced_nightly = values.is_poa || !values.reduced_nightly ? null : values.reduced_nightly;
  const reduced_weekly = values.is_poa || !values.reduced_weekly ? null : values.reduced_weekly;
  const hasReduction =
    reduction_percent !== null || reduced_nightly !== null || reduced_weekly !== null;
  return {
    ...values,
    nightly: values.is_poa || !values.nightly ? null : values.nightly,
    weekly: values.is_poa || !values.weekly ? null : values.weekly,
    reduction_percent,
    reduced_nightly,
    reduced_weekly,
    // Metadata may only ride alongside a live reduction (the server 400s it
    // otherwise) and must clear with it. `reduction_reason` clears to "" —
    // the backend column is a non-nullable CharField.
    reduced_at: hasReduction && values.reduced_at ? values.reduced_at : null,
    reduction_reason: hasReduction ? (values.reduction_reason ?? "") : "",
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

/** Q-018: live preview of the price quoting will actually charge once the
 * typed reduction applies. Mirrors `DerivedCounterpartHint`: display-only,
 * renders nothing when the currency is unknown or nothing is derivable. */
function EffectivePriceHint({
  base,
  percent,
  reduced,
  label,
  currencyCode,
}: {
  base: string | undefined;
  percent?: string;
  reduced?: string;
  label: string;
  currencyCode?: string | null;
}) {
  if (!currencyCode || !base || !MONEY_PATTERN.test(base)) return null;
  const baseAmount = Number(base);
  let effective: number | null = null;
  if (percent && PERCENT_PATTERN.test(percent)) {
    const pct = Number(percent);
    if (pct > 0 && pct < 100) effective = roundHalfEven(baseAmount * (1 - pct / 100));
  } else if (reduced && MONEY_PATTERN.test(reduced)) {
    const amount = Number(reduced);
    if (amount > 0 && amount < baseAmount) effective = amount;
  }
  if (effective == null) return null;
  return (
    <p className="text-muted-foreground text-xs" data-testid="effective-price">
      {label}: {formatMoney(effective, currencyCode)}
    </p>
  );
}

export function RateBandFormDialog(props: RateBandFormDialogProps) {
  const {
    ratePlanId,
    periodId,
    open,
    onOpenChange,
    currencyCode,
    priceBasis,
    commission,
    tax,
    pricesByOccupancy = true,
    capacity,
  } = props;
  const { t } = useTranslation("properties");
  const isCreate = props.mode === "create";
  const priceAdornment = currencyAdornment(currencyCode);

  // Flat plans price one rate per period (party ignored). Hide the party inputs
  // and pin the single band to span the whole party range so any-size bookings
  // still price — the engine matches party against the band even when flat.
  const flatSeed: Partial<RateBandWriteInput> = { min_party: 1, max_party: capacity ?? 1 };
  const buildCreateDefaults = (seed?: Partial<RateBandWriteInput>) =>
    createDefaults(pricesByOccupancy ? seed : { ...seed, ...flatSeed });

  const form = useForm<RateBandWriteInput>({
    resolver: zodResolver(rateBandWriteInputSchema),
    defaultValues: isCreate ? buildCreateDefaults(props.defaults) : defaultsFromRule(props.rule),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  // Q-018: which reduction editor is showing. Derived from the loaded values
  // and re-derived whenever the dialog (re)opens.
  const [reductionKind, setReductionKind] = useState<ReductionKind>(() =>
    reductionKindOf(form.getValues()),
  );

  const createMutation = useCreateRateBand(ratePlanId);
  const updateMutation = useUpdateRateBand(ratePlanId);
  const submitting = createMutation.isPending || updateMutation.isPending;

  useEffect(() => {
    if (open) {
      const values = isCreate ? buildCreateDefaults(props.defaults) : defaultsFromRule(props.rule);
      form.reset(values);
      setReductionKind(reductionKindOf(values));
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? null : props.rule.id]);

  /** Switching reduction mode clears the other mode's inputs (leftovers must
   * never fail the XOR refine) and stamps today on first enable. */
  const switchReductionKind = (next: ReductionKind) => {
    setReductionKind(next);
    if (next !== "percent") form.setValue("reduction_percent", "");
    if (next !== "fixed") {
      form.setValue("reduced_nightly", "");
      form.setValue("reduced_weekly", "");
    }
    if (next === "none") {
      form.setValue("reduced_at", "");
      form.setValue("reduction_reason", "");
    } else if (!form.getValues("reduced_at")) {
      form.setValue("reduced_at", todayIso());
    }
    form.clearErrors(["reduction_percent", "reduced_nightly", "reduced_weekly"]);
  };

  /** A cleared base price takes its fixed reduced amount with it — RHF keeps
   * unmounted values, so a stale reduced_* would otherwise fail the no-base
   * refine on a hidden input and silently block the save. */
  const clearReducedWhenBaseEmpty =
    (reducedField: "reduced_nightly" | "reduced_weekly") =>
    (event: ChangeEvent<HTMLInputElement>) => {
      if (!event.target.value.trim() && form.getValues(reducedField)) {
        form.setValue(reducedField, "");
        form.clearErrors(reducedField);
      }
    };

  /** A picked reduction mode with its amount left blank would pass the schema
   * as "no reduction" and silently discard the typed metadata — demand the
   * amount (or an explicit switch back to "No reduction") instead. */
  const guardIncompleteReduction = (values: RateBandWriteInput): boolean => {
    if (values.is_poa || reductionKind === "none") return false;
    if (reductionKind === "percent") {
      if (values.reduction_percent) return false;
      form.setError("reduction_percent", {
        message: "properties:errors.reduction_value_required",
      });
      return true;
    }
    const rendered = (
      [
        ["reduced_nightly", values.nightly],
        ["reduced_weekly", values.weekly],
      ] as const
    ).filter(([, base]) => Boolean(base));
    if (rendered.length === 0 || rendered.some(([field]) => values[field])) return false;
    form.setError(rendered[0][0], { message: "properties:errors.reduction_value_required" });
    return true;
  };

  const submit = async (values: RateBandWriteInput, andAddAnother: boolean) => {
    setTopLevelError(null);
    if (guardIncompleteReduction(values)) return;
    try {
      if (isCreate) {
        await createMutation.mutateAsync({ periodId, input: toPayload(values) });
        toast.success(t("pricing.rule.toasts.created"));
      } else {
        await updateMutation.mutateAsync({ bandId: props.rule.id, input: toPayload(values) });
        toast.success(t("pricing.rule.toasts.updated"));
      }
      if (andAddAnother) {
        // Bands cover disjoint party ranges within a period — seed the next one
        // just above this band's max, so building 1–2 / 3–4 / … coverage is fast.
        const nextParty = (values.max_party ?? 0) + 1;
        form.reset(createDefaults({ min_party: nextParty, max_party: nextParty }));
        setReductionKind("none");
        form.setFocus("min_party");
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
  const reductionPercent = form.watch("reduction_percent");
  const reducedNightly = form.watch("reduced_nightly");
  const reducedWeekly = form.watch("reduced_weekly");

  // Server 400s can key a reduction field whose input isn't currently mounted
  // (e.g. reduction_percent while the kind selector says none/fixed) — RHF
  // would hold the error invisibly, so surface those in one aggregate line.
  const reductionFieldMounted: Record<(typeof REDUCTION_FIELDS)[number], boolean> = {
    reduction_percent: reductionKind === "percent",
    reduced_nightly: reductionKind === "fixed" && Boolean(nightly),
    reduced_weekly: reductionKind === "fixed" && Boolean(weekly),
    reduced_at: reductionKind !== "none",
    reduction_reason: reductionKind !== "none",
  };
  const hiddenReductionErrors = REDUCTION_FIELDS.filter(
    (field) => !reductionFieldMounted[field] && form.formState.errors[field]?.message,
  ).map((field) => fieldErrorText(t, form.formState.errors[field]?.message));

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
          {/* Party bands only apply to occupancy pricing. A flat plan has one
              band spanning the whole party range (auto-set to 1..capacity), so
              the inputs are hidden rather than asked for. */}
          {pricesByOccupancy ? (
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
          ) : null}

          <div className="flex items-center gap-2">
            <Checkbox
              id="rate-rule-is-poa"
              checked={isPoa}
              onCheckedChange={(v) => {
                form.setValue("is_poa", v === true);
                // Price (and reduction — a POA band can't carry one) errors
                // no longer apply once POA masks the inputs.
                form.clearErrors([
                  "nightly",
                  "weekly",
                  "reduction_percent",
                  "reduced_nightly",
                  "reduced_weekly",
                ]);
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
                {...form.register("nightly", {
                  onChange: clearReducedWhenBaseEmpty("reduced_nightly"),
                })}
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
                {...form.register("weekly", {
                  onChange: clearReducedWhenBaseEmpty("reduced_weekly"),
                })}
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

          {/* Q-018: a reduction keeps the base prices above intact and quotes
              the effective price instead. Hidden under POA — a POA band has
              no price to reduce (the payload nulls any leftovers). */}
          {!isPoa ? (
            <div className="space-y-3">
              <div className="space-y-2">
                <Label htmlFor="rate-rule-reduction-kind">
                  {t("pricing.rule.dialog.reduction.kind")}
                </Label>
                <Select
                  value={reductionKind}
                  onValueChange={(v) => switchReductionKind(v as ReductionKind)}
                >
                  <SelectTrigger id="rate-rule-reduction-kind">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">
                      {t("pricing.rule.dialog.reduction.kind_none")}
                    </SelectItem>
                    <SelectItem value="percent">
                      {t("pricing.rule.dialog.reduction.kind_percent")}
                    </SelectItem>
                    <SelectItem value="fixed">
                      {t("pricing.rule.dialog.reduction.kind_fixed")}
                    </SelectItem>
                  </SelectContent>
                </Select>
                {hiddenReductionErrors.length > 0 ? (
                  <p className="text-destructive text-sm" role="alert">
                    {hiddenReductionErrors.join(" ")}
                  </p>
                ) : null}
              </div>

              {reductionKind === "percent" ? (
                <div className="space-y-2">
                  <Label htmlFor="rate-rule-reduction-percent">
                    {t("pricing.rule.dialog.reduction.percent")}
                  </Label>
                  <Input
                    id="rate-rule-reduction-percent"
                    inputMode="decimal"
                    {...form.register("reduction_percent")}
                  />
                  {form.formState.errors.reduction_percent ? (
                    <p className="text-destructive text-sm" role="alert">
                      {fieldErrorText(t, form.formState.errors.reduction_percent.message)}
                    </p>
                  ) : null}
                  <EffectivePriceHint
                    base={nightly}
                    percent={reductionPercent}
                    label={t("pricing.rule.dialog.reduction.effective_nightly")}
                    currencyCode={currencyCode}
                  />
                  <EffectivePriceHint
                    base={weekly}
                    percent={reductionPercent}
                    label={t("pricing.rule.dialog.reduction.effective_weekly")}
                    currencyCode={currencyCode}
                  />
                </div>
              ) : null}

              {/* Fixed mode asks for a new amount per non-empty base price —
                  decision 6b: a fixed reduction must cover every base. */}
              {reductionKind === "fixed" ? (
                <div className="grid grid-cols-2 gap-3">
                  {nightly ? (
                    <div className="space-y-2">
                      <Label htmlFor="rate-rule-reduced-nightly">
                        {t("pricing.rule.dialog.reduction.reduced_nightly")}
                      </Label>
                      <MoneyInput
                        id="rate-rule-reduced-nightly"
                        inputMode="decimal"
                        adornment={priceAdornment}
                        {...form.register("reduced_nightly")}
                      />
                      {form.formState.errors.reduced_nightly ? (
                        <p className="text-destructive text-sm" role="alert">
                          {fieldErrorText(t, form.formState.errors.reduced_nightly.message)}
                        </p>
                      ) : null}
                      <EffectivePriceHint
                        base={nightly}
                        reduced={reducedNightly}
                        label={t("pricing.rule.dialog.reduction.effective_nightly")}
                        currencyCode={currencyCode}
                      />
                    </div>
                  ) : null}
                  {weekly ? (
                    <div className="space-y-2">
                      <Label htmlFor="rate-rule-reduced-weekly">
                        {t("pricing.rule.dialog.reduction.reduced_weekly")}
                      </Label>
                      <MoneyInput
                        id="rate-rule-reduced-weekly"
                        inputMode="decimal"
                        adornment={priceAdornment}
                        {...form.register("reduced_weekly")}
                      />
                      {form.formState.errors.reduced_weekly ? (
                        <p className="text-destructive text-sm" role="alert">
                          {fieldErrorText(t, form.formState.errors.reduced_weekly.message)}
                        </p>
                      ) : null}
                      <EffectivePriceHint
                        base={weekly}
                        reduced={reducedWeekly}
                        label={t("pricing.rule.dialog.reduction.effective_weekly")}
                        currencyCode={currencyCode}
                      />
                    </div>
                  ) : null}
                </div>
              ) : null}

              {reductionKind !== "none" ? (
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-2">
                    <Label htmlFor="rate-rule-reduced-at">
                      {t("pricing.rule.dialog.reduction.reduced_at")}
                    </Label>
                    <Input id="rate-rule-reduced-at" type="date" {...form.register("reduced_at")} />
                    {form.formState.errors.reduced_at ? (
                      <p className="text-destructive text-sm" role="alert">
                        {fieldErrorText(t, form.formState.errors.reduced_at.message)}
                      </p>
                    ) : null}
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="rate-rule-reduction-reason">
                      {t("pricing.rule.dialog.reduction.reason")}
                    </Label>
                    <Input
                      id="rate-rule-reduction-reason"
                      maxLength={200}
                      {...form.register("reduction_reason")}
                    />
                    {form.formState.errors.reduction_reason ? (
                      <p className="text-destructive text-sm" role="alert">
                        {fieldErrorText(t, form.formState.errors.reduction_reason.message)}
                      </p>
                    ) : null}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}

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
            {/* A flat plan allows only one band (the backend 400s a second), so
                "save and add another" is offered for occupancy pricing only. */}
            {isCreate && pricesByOccupancy ? (
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
