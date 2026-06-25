import { useEffect, useState } from "react";
import { useFieldArray, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/errors";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { formatMoney } from "@/lib/format/money";
import { fieldErrorText } from "@/lib/forms/fieldError";
import type { BookingId } from "@/lib/query/keys";
import { useCreateDamageClaim, useUpdateDamageClaim } from "../hooks";
import {
  damageClaimWriteInputSchema,
  type DamageClaim,
  type DamageClaimWriteInput,
} from "../schemas";

interface CommonProps {
  bookingId: BookingId;
  currencyCode: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface CreateProps extends CommonProps {
  mode: "create";
}

interface EditProps extends CommonProps {
  mode: "edit";
  claim: DamageClaim;
}

type Props = CreateProps | EditProps;

const createDefaults: DamageClaimWriteInput = { description: "", amount: "", itemized_lines: [] };

function defaultsFromClaim(claim: DamageClaim): DamageClaimWriteInput {
  return {
    description: claim.description,
    amount: claim.amount,
    itemized_lines: claim.itemized_lines.map((line) => ({
      label: line.label,
      amount: line.amount,
    })),
  };
}

export function DamageClaimFormDialog(props: Props) {
  const { t } = useTranslation("bookings");
  const { bookingId, currencyCode, open, onOpenChange } = props;
  const isCreate = props.mode === "create";

  const form = useForm<DamageClaimWriteInput>({
    resolver: zodResolver(damageClaimWriteInputSchema),
    defaultValues: isCreate ? createDefaults : defaultsFromClaim(props.claim),
  });
  const lines = useFieldArray({ control: form.control, name: "itemized_lines" });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  const createMutation = useCreateDamageClaim(bookingId);
  const updateMutation = useUpdateDamageClaim(bookingId);
  const submitting = createMutation.isPending || updateMutation.isPending;

  const idleSubmitLabel = isCreate
    ? t("damage_claims.form_dialog.submit_create")
    : t("common:actions.save");

  // Running total of the itemised breakdown — display-only; it need not equal
  // the claim amount (the money that moves is the SD capture, not this sum).
  const watchedLines = form.watch("itemized_lines");
  const linesTotal = watchedLines.reduce((sum, line) => {
    const n = Number(line.amount);
    return Number.isFinite(n) ? sum + n : sum;
  }, 0);

  useEffect(() => {
    if (open) {
      form.reset(isCreate ? createDefaults : defaultsFromClaim(props.claim));
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? null : props.claim.id]);

  const handleSubmit = async (values: DamageClaimWriteInput) => {
    setTopLevelError(null);
    try {
      if (isCreate) {
        await createMutation.mutateAsync(values);
      } else {
        await updateMutation.mutateAsync({ claimId: props.claim.id, input: values });
      }
      toast.success(isCreate ? t("damage_claims.toasts.filed") : t("damage_claims.toasts.updated"));
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        setTopLevelError(detail);
      } else {
        toast.error(t("common:errors.generic"));
      }
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isCreate
              ? t("damage_claims.form_dialog.create_title")
              : t("damage_claims.form_dialog.edit_title")}
          </DialogTitle>
          <DialogDescription>{t("damage_claims.form_dialog.description")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="claim-description">
              {t("damage_claims.form_dialog.fields.description")}
            </Label>
            <Textarea
              id="claim-description"
              rows={3}
              autoFocus
              {...form.register("description")}
              aria-invalid={!!form.formState.errors.description}
            />
            {form.formState.errors.description ? (
              <p className="text-destructive text-sm" role="alert">
                {fieldErrorText(t, form.formState.errors.description.message)}
              </p>
            ) : null}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="claim-amount">{t("damage_claims.form_dialog.fields.amount")}</Label>
              <Input
                id="claim-amount"
                inputMode="decimal"
                placeholder="500.00"
                {...form.register("amount")}
                aria-invalid={!!form.formState.errors.amount}
              />
              {form.formState.errors.amount ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.amount.message)}
                </p>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label>{t("damage_claims.form_dialog.fields.currency")}</Label>
              {/* Pinned to the booking's currency server-side; shown for clarity. */}
              <p className="text-muted-foreground flex h-9 items-center text-sm">
                {currencyCode ?? "—"}
              </p>
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>{t("damage_claims.form_dialog.itemized.heading")}</Label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => lines.append({ label: "", amount: "" })}
              >
                {t("damage_claims.form_dialog.itemized.add_line")}
              </Button>
            </div>
            {lines.fields.map((field, index) => (
              <div key={field.id} className="flex items-start gap-2">
                <div className="flex-1">
                  <Input
                    aria-label={t("damage_claims.form_dialog.itemized.line_label", {
                      n: index + 1,
                    })}
                    placeholder={t("damage_claims.form_dialog.itemized.label_placeholder")}
                    {...form.register(`itemized_lines.${index}.label`)}
                  />
                  {form.formState.errors.itemized_lines?.[index]?.label ? (
                    <p className="text-destructive text-sm" role="alert">
                      {fieldErrorText(
                        t,
                        form.formState.errors.itemized_lines[index]?.label?.message,
                      )}
                    </p>
                  ) : null}
                </div>
                <div className="w-28">
                  <Input
                    inputMode="decimal"
                    aria-label={t("damage_claims.form_dialog.itemized.line_amount", {
                      n: index + 1,
                    })}
                    placeholder="0.00"
                    {...form.register(`itemized_lines.${index}.amount`)}
                  />
                  {form.formState.errors.itemized_lines?.[index]?.amount ? (
                    <p className="text-destructive text-sm" role="alert">
                      {fieldErrorText(
                        t,
                        form.formState.errors.itemized_lines[index]?.amount?.message,
                      )}
                    </p>
                  ) : null}
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="text-destructive"
                  aria-label={t("damage_claims.form_dialog.itemized.remove_line", { n: index + 1 })}
                  onClick={() => lines.remove(index)}
                >
                  {t("common:actions.remove")}
                </Button>
              </div>
            ))}
            {lines.fields.length > 0 ? (
              <p className="text-muted-foreground text-right text-sm">
                {t("damage_claims.form_dialog.itemized.lines_total", {
                  total: formatMoney(linesTotal, currencyCode),
                })}
              </p>
            ) : null}
          </div>

          {topLevelError ? (
            <p className="text-destructive text-sm" role="alert">
              {topLevelError}
            </p>
          ) : null}

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t("common:actions.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? t("common:actions.saving") : idleSubmitLabel}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
