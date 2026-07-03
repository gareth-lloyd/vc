import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api/errors";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { fieldErrorText } from "@/lib/forms/fieldError";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import type { RatePlanDetail } from "@/features/properties/schemas";
import { useCarryForwardRatePlan } from "../hooks";
import { carryForwardInputSchema, type CarryForwardInput } from "../schemas";

// Blank uplift means "copy unchanged" (0), not null — so it differs from the
// shared `asNumberOrNull`; the number field otherwise yields a real number.
const asUpliftNumber = (v: unknown) => (v === "" || v == null ? 0 : Number(v));

interface CarryForwardDialogProps {
  propertyId: number;
  /** The active plan's Currency CODE (e.g. "GBP") — the endpoint resolves by
   * code, so the numeric FK id must never be sent. */
  currencyCode: string;
  targetYear: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCarried: (plan: RatePlanDetail) => void;
}

/**
 * Promote a projected future year into real, editable rate rows (GAP-069). The
 * only user input is the uplift %; the currency and target year are contextual
 * and shown read-only. A 409 `no_rate_available` (no prior year to carry from)
 * renders inline; other 4xx map to field errors; 5xx toast.
 */
export function CarryForwardDialog({
  propertyId,
  currencyCode,
  targetYear,
  open,
  onOpenChange,
  onCarried,
}: CarryForwardDialogProps) {
  const { t } = useTranslation("properties");
  const form = useForm<CarryForwardInput>({
    resolver: zodResolver(carryForwardInputSchema),
    defaultValues: { uplift_pct: 0 },
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  const [noRates, setNoRates] = useState(false);

  const mutation = useCarryForwardRatePlan(propertyId);
  const submitting = mutation.isPending;

  useEffect(() => {
    if (!open) return;
    form.reset({ uplift_pct: 0 });
    setTopLevelError(null);
    setNoRates(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const handleSubmit = async (values: CarryForwardInput) => {
    setTopLevelError(null);
    setNoRates(false);
    try {
      const plan = await mutation.mutateAsync({
        currency: currencyCode,
        target_year: targetYear,
        uplift_pct: values.uplift_pct,
      });
      toast.success(t("rate_workbench.carry_forward.toasts.success", { year: targetYear }));
      onCarried(plan);
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.code === "no_rate_available") {
        // Domain "nothing to carry" — stay open, no toast, explain inline.
        setNoRates(true);
      } else if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        setTopLevelError(detail);
      } else {
        toast.error(t("rate_workbench.carry_forward.toasts.failed"));
      }
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {t("rate_workbench.carry_forward.dialog_title", { year: targetYear })}
          </DialogTitle>
          <DialogDescription>
            {t("rate_workbench.carry_forward.dialog_description", { year: targetYear })}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <p className="text-muted-foreground text-sm">
            {t("rate_workbench.carry_forward.summary", {
              year: targetYear,
              currency: currencyCode,
            })}
          </p>

          <div className="space-y-2">
            <Label htmlFor="carry-uplift">{t("rate_workbench.carry_forward.uplift_label")}</Label>
            <Input
              id="carry-uplift"
              type="number"
              inputMode="decimal"
              min={0}
              step="0.1"
              {...form.register("uplift_pct", { setValueAs: asUpliftNumber })}
            />
            <p className="text-muted-foreground text-xs">
              {t("rate_workbench.carry_forward.uplift_hint")}
            </p>
            {form.formState.errors.uplift_pct ? (
              <p className="text-destructive text-sm" role="alert">
                {fieldErrorText(t, form.formState.errors.uplift_pct.message)}
              </p>
            ) : null}
          </div>

          {noRates ? (
            <p
              className="border-warning/40 bg-warning/10 text-warning rounded-md border px-3 py-2 text-sm"
              role="alert"
            >
              {t("rate_workbench.carry_forward.no_rates")}
            </p>
          ) : null}

          <FormErrorAlert message={topLevelError} />

          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              {t("rate_workbench.carry_forward.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting
                ? t("rate_workbench.carry_forward.submitting")
                : t("rate_workbench.carry_forward.submit")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
