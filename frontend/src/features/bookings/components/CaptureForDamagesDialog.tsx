import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/lib/api/errors";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { formatMoney, parseMoney } from "@/lib/format/money";
import { fieldErrorText } from "@/lib/forms/fieldError";
import type { BookingId } from "@/lib/query/keys";
import { useBookingDamageClaims, useCaptureSecurityDepositForDamages } from "../hooks";
import {
  captureForDamagesInputSchema,
  type CaptureForDamagesInput,
  type SecurityDeposit,
} from "../schemas";

interface Props {
  bookingId: BookingId;
  deposit: SecurityDeposit;
  currencyCode: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CaptureForDamagesDialog({
  bookingId,
  deposit,
  currencyCode,
  open,
  onOpenChange,
}: Props) {
  const { t } = useTranslation("bookings");
  const claims = useBookingDamageClaims(bookingId);
  const captureMutation = useCaptureSecurityDepositForDamages(bookingId);
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  // Only OPEN claims are offerable — a withdrawn/settled claim shouldn't justify
  // a fresh capture. The backend accepts any same-booking claim, so this is a UI
  // nicety, not a guard.
  const openClaims = (claims.data?.results ?? []).filter((c) => c.status === "open");

  // The capture may never exceed the held amount (the backend would 409, and a
  // BT over-capture inverts the refund). Bound it in the FE so the operator sees
  // it inline before submitting.
  const schema = captureForDamagesInputSchema.refine(
    (v) => parseMoney(v.captured_amount) <= parseMoney(deposit.amount),
    {
      message: "bookings:schema_errors.capture_exceeds_amount",
      path: ["captured_amount"],
    },
  );

  const form = useForm<CaptureForDamagesInput>({
    resolver: zodResolver(schema),
    defaultValues: { damage_claim: undefined, captured_amount: "" },
  });

  useEffect(() => {
    if (open) {
      form.reset({ damage_claim: undefined, captured_amount: "" });
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const selectedClaimId = form.watch("damage_claim");

  // Picking a claim defaults the capture to that claim's amount — the common
  // case is "capture the whole claimed amount"; the operator can still edit it.
  const handleClaimChange = (value: string) => {
    const id = Number(value);
    form.setValue("damage_claim", id, { shouldValidate: true });
    const claim = openClaims.find((c) => c.id === id);
    if (claim) form.setValue("captured_amount", claim.amount, { shouldValidate: true });
  };

  const handleSubmit = async (values: CaptureForDamagesInput) => {
    setTopLevelError(null);
    try {
      await captureMutation.mutateAsync(values);
      toast.success(t("security_deposit.toasts.captured"));
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
          <DialogTitle>{t("security_deposit.capture_dialog.title")}</DialogTitle>
          <DialogDescription>
            {t("security_deposit.capture_dialog.description", {
              amount: formatMoney(deposit.amount, currencyCode),
            })}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="capture-claim">
              {t("security_deposit.capture_dialog.fields.claim")}
            </Label>
            {openClaims.length === 0 ? (
              <p className="text-muted-foreground text-sm">
                {t("security_deposit.capture_dialog.no_open_claims")}
              </p>
            ) : (
              <Select
                value={selectedClaimId ? String(selectedClaimId) : undefined}
                onValueChange={handleClaimChange}
              >
                <SelectTrigger
                  id="capture-claim"
                  aria-invalid={!!form.formState.errors.damage_claim}
                >
                  <SelectValue
                    placeholder={t("security_deposit.capture_dialog.fields.claim_placeholder")}
                  />
                </SelectTrigger>
                <SelectContent>
                  {openClaims.map((claim) => (
                    <SelectItem key={claim.id} value={String(claim.id)}>
                      {claim.reference} ·{" "}
                      {formatMoney(claim.amount, claim.currency_code ?? currencyCode)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            {form.formState.errors.damage_claim ? (
              <p className="text-destructive text-sm" role="alert">
                {fieldErrorText(t, form.formState.errors.damage_claim.message)}
              </p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="capture-amount">
              {t("security_deposit.capture_dialog.fields.captured_amount")}
            </Label>
            <Input
              id="capture-amount"
              inputMode="decimal"
              placeholder="0.00"
              {...form.register("captured_amount")}
              aria-invalid={!!form.formState.errors.captured_amount}
            />
            {form.formState.errors.captured_amount ? (
              <p className="text-destructive text-sm" role="alert">
                {fieldErrorText(t, form.formState.errors.captured_amount.message)}
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
            <Button type="submit" disabled={captureMutation.isPending || openClaims.length === 0}>
              {captureMutation.isPending
                ? t("common:actions.saving")
                : t("security_deposit.capture_dialog.submit")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
