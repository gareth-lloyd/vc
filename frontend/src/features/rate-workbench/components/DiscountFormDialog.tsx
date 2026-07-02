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
import { ApiError } from "@/lib/api/errors";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { fieldErrorText } from "@/lib/forms/fieldError";
import { currencyAdornment } from "@/lib/format/money";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { useCreateDiscount, useUpdateDiscount } from "../hooks";
import {
  DISCOUNT_KINDS,
  RULE_KINDS,
  THRESHOLD_RULE_KINDS,
  discountWriteInputSchema,
  type DiscountWriteInput,
  type DiscountWritePayload,
} from "../schemas";
import { EnumSelect } from "./EnumSelect";
import type { Discount } from "@/features/properties/schemas";

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
  entity: Discount;
}

type DiscountFormDialogProps = CreateProps | EditProps;

// Sensible enum defaults so a new discount is savable without forcing a pick for
// every field (mirrors the season dialog defaulting price_basis).
const CREATE_DEFAULTS: DiscountWriteInput = {
  name: "",
  code: "",
  rule_kind: "promo_code",
  kind: "percent",
  amount: "",
  min_nights: null,
  threshold_days: null,
  valid_from: "",
  valid_to: "",
  max_uses: null,
  is_active: true,
};

function defaultsFromDiscount(discount: Discount): DiscountWriteInput {
  return {
    name: discount.name,
    code: discount.code ?? "",
    rule_kind: discount.rule_kind ?? "promo_code",
    kind: discount.kind ?? "percent",
    amount: discount.amount ?? "",
    // The column is NOT NULL default 0, so a stored 0 means "no minimum" —
    // present it as the blank input the operator originally left.
    min_nights: discount.min_nights || null,
    threshold_days: discount.threshold_days ?? null,
    valid_from: discount.valid_from ?? "",
    valid_to: discount.valid_to ?? "",
    max_uses: discount.max_uses ?? null,
    is_active: discount.is_active ?? true,
  };
}

const isThresholdKind = (ruleKind: string) =>
  (THRESHOLD_RULE_KINDS as readonly string[]).includes(ruleKind);

function toPayload(values: DiscountWriteInput): DiscountWritePayload {
  // `amount`/dates are required (schema-guaranteed). An empty `code` collapses
  // to `null`, never "" — the model's UNIQUE index treats "" as a real value
  // that a second code-less discount would collide on, but allows many NULLs.
  // Note: hidden fields (code / threshold_days for the "wrong" rule kind) are
  // deliberately submitted as-is, never nulled — the rule-kind switch handler
  // restores them to their stored values, so an edit can't silently wipe a
  // live promo code the engine merely ignores for the current kind.
  return {
    ...values,
    code: values.code ? values.code : null,
  };
}

/** RHF number field: "" → null, else Number — keeps the zod number|null happy. */
const asNumberOrNull = (v: unknown) => (v === "" || v == null ? null : Number(v));

export function DiscountFormDialog(props: DiscountFormDialogProps) {
  const { propertyId, open, onOpenChange, currencyCode } = props;
  const { t } = useTranslation("properties");
  const isCreate = props.mode === "create";
  const amountAdornment = currencyAdornment(currencyCode);

  const form = useForm<DiscountWriteInput>({
    resolver: zodResolver(discountWriteInputSchema),
    defaultValues: isCreate ? CREATE_DEFAULTS : defaultsFromDiscount(props.entity),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  const createMutation = useCreateDiscount(propertyId);
  const updateMutation = useUpdateDiscount(propertyId);
  const submitting = createMutation.isPending || updateMutation.isPending;

  useEffect(() => {
    if (open) {
      form.reset(isCreate ? CREATE_DEFAULTS : defaultsFromDiscount(props.entity));
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? null : props.entity.id]);

  const handleSubmit = async (values: DiscountWriteInput) => {
    setTopLevelError(null);
    const body = toPayload(values);
    try {
      if (isCreate) {
        await createMutation.mutateAsync(body);
        toast.success(t("rate_workbench.inspector.toasts.created"));
      } else {
        await updateMutation.mutateAsync({ discountId: props.entity.id, input: body });
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

  const ruleKind = form.watch("rule_kind");
  const kind = form.watch("kind");
  const isActive = form.watch("is_active") ?? true;

  // Switching rule kind hides the irrelevant field (code / threshold_days).
  // Restore hidden fields to their pristine (stored or default) values so a
  // half-typed or stale value can neither be submitted invisibly nor block
  // validation from inside an unmounted branch.
  const handleRuleKindChange = (v: string) => {
    const pristine = isCreate ? CREATE_DEFAULTS : defaultsFromDiscount(props.entity);
    if ((v === "promo_code") !== (ruleKind === "promo_code")) {
      form.setValue("code", pristine.code);
      form.clearErrors("code");
    }
    if (isThresholdKind(v) !== isThresholdKind(ruleKind)) {
      form.setValue("threshold_days", pristine.threshold_days);
      form.clearErrors("threshold_days");
    }
    form.setValue("rule_kind", v, { shouldValidate: true });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isCreate
              ? t("rate_workbench.inspector.discount_dialog.create_title")
              : t("rate_workbench.inspector.discount_dialog.edit_title")}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="discount-name">{t("rate_workbench.inspector.fields.name")}</Label>
            <Input id="discount-name" {...form.register("name")} />
            {form.formState.errors.name ? (
              <p className="text-destructive text-sm" role="alert">
                {fieldErrorText(t, form.formState.errors.name.message)}
              </p>
            ) : null}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="discount-rule-kind">
                {t("rate_workbench.inspector.fields.rule_kind")}
              </Label>
              <EnumSelect
                id="discount-rule-kind"
                value={ruleKind}
                onChange={handleRuleKindChange}
                options={RULE_KINDS}
                labelFor={(v) => t(`rate_workbench.inspector.enums.rule_kind.${v}`)}
              />
              {form.formState.errors.rule_kind ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.rule_kind.message)}
                </p>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="discount-kind">{t("rate_workbench.inspector.fields.kind")}</Label>
              <EnumSelect
                id="discount-kind"
                value={kind}
                onChange={(v) => form.setValue("kind", v, { shouldValidate: true })}
                options={DISCOUNT_KINDS}
                labelFor={(v) => t(`rate_workbench.inspector.enums.discount_kind.${v}`)}
              />
              {form.formState.errors.kind ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.kind.message)}
                </p>
              ) : null}
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-2">
              <Label htmlFor="discount-amount">{t("rate_workbench.inspector.fields.amount")}</Label>
              <MoneyInput
                id="discount-amount"
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
            {/* One grid cell whose contents follow the rule kind: promo codes
                get the Code input, lead-time kinds get the threshold (with a
                direction-specific label — early bird is a minimum lead time,
                last minute a maximum), other kinds leave the slot empty. */}
            <div className="space-y-2">
              {ruleKind === "promo_code" ? (
                <>
                  <Label htmlFor="discount-code">{t("rate_workbench.inspector.fields.code")}</Label>
                  <Input id="discount-code" {...form.register("code")} />
                  {form.formState.errors.code ? (
                    <p className="text-destructive text-sm" role="alert">
                      {fieldErrorText(t, form.formState.errors.code.message)}
                    </p>
                  ) : null}
                </>
              ) : isThresholdKind(ruleKind) ? (
                <>
                  <Label htmlFor="discount-threshold-days">
                    {t(`rate_workbench.inspector.fields.threshold_days_${ruleKind}`)}
                  </Label>
                  <Input
                    id="discount-threshold-days"
                    type="number"
                    min={0}
                    {...form.register("threshold_days", { setValueAs: asNumberOrNull })}
                  />
                  {form.formState.errors.threshold_days ? (
                    <p className="text-destructive text-sm" role="alert">
                      {fieldErrorText(t, form.formState.errors.threshold_days.message)}
                    </p>
                  ) : null}
                </>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="discount-min-nights">
                {t("rate_workbench.inspector.fields.min_nights")}
              </Label>
              <Input
                id="discount-min-nights"
                type="number"
                min={0}
                {...form.register("min_nights", { setValueAs: asNumberOrNull })}
              />
              {form.formState.errors.min_nights ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.min_nights.message)}
                </p>
              ) : null}
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-2">
              <Label htmlFor="discount-valid-from">
                {t("rate_workbench.inspector.fields.valid_from")}
              </Label>
              <Input id="discount-valid-from" type="date" {...form.register("valid_from")} />
              {form.formState.errors.valid_from ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.valid_from.message)}
                </p>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="discount-valid-to">
                {t("rate_workbench.inspector.fields.valid_to")}
              </Label>
              <Input id="discount-valid-to" type="date" {...form.register("valid_to")} />
              {form.formState.errors.valid_to ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.valid_to.message)}
                </p>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="discount-max-uses">
                {t("rate_workbench.inspector.fields.max_uses")}
              </Label>
              <Input
                id="discount-max-uses"
                type="number"
                min={0}
                {...form.register("max_uses", { setValueAs: asNumberOrNull })}
              />
              {form.formState.errors.max_uses ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.max_uses.message)}
                </p>
              ) : null}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Checkbox
              id="discount-is-active"
              checked={isActive}
              onCheckedChange={(v) => form.setValue("is_active", v === true)}
            />
            <Label htmlFor="discount-is-active">
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
