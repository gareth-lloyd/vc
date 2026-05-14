import { useEffect, useState } from "react";
import { useController, useForm } from "react-hook-form";
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
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/errors";
import { applyApiErrorToForm } from "@/lib/api/forms";
import type { BookingId } from "@/lib/query/keys";
import type { TrackName } from "../api";
import { useMarkPaid, useWaiveTrack } from "../hooks";
import {
  markPaidInputSchema,
  paymentMethodOptions,
  waiveTrackInputSchema,
  type MarkPaidInput,
  type WaiveTrackInput,
} from "../schemas";

interface CommonProps {
  bookingId: BookingId;
  track: TrackName;
  trackLabel: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Pre-fill the amount field on mark-paid. Pass the remaining-due figure. */
  defaultAmount?: string;
}

type Props = (CommonProps & { action: "mark-paid" }) | (CommonProps & { action: "waive" });

function todayLocalDatetime(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function MarkPaidForm({ bookingId, track, trackLabel, onOpenChange, defaultAmount }: CommonProps) {
  const { t } = useTranslation("bookings");
  const defaults: MarkPaidInput = {
    amount: defaultAmount ?? "",
    paid_at: todayLocalDatetime(),
    method: "bank_transfer",
    reference: "",
    notes: "",
  };
  const form = useForm<MarkPaidInput>({
    resolver: zodResolver(markPaidInputSchema),
    defaultValues: defaults,
  });
  const methodCtrl = useController({ control: form.control, name: "method" });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  const mutation = useMarkPaid(bookingId, track);

  const methodOptions = paymentMethodOptions();

  const handleSubmit = async (values: MarkPaidInput) => {
    setTopLevelError(null);
    try {
      // Backend expects ISO 8601 — append seconds + Z if the input gave us the
      // datetime-local shape (`YYYY-MM-DDTHH:mm`).
      const paid_at = /T\d{2}:\d{2}$/.test(values.paid_at)
        ? new Date(values.paid_at).toISOString()
        : values.paid_at;
      await mutation.mutateAsync({ ...values, paid_at });
      toast.success(t("payments.mark_paid_dialog.success_message", { track: trackLabel }));
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
    <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
      <div className="space-y-2">
        <Label htmlFor="markpaid-amount">{t("payments.mark_paid_dialog.fields.amount")}</Label>
        <Input
          id="markpaid-amount"
          inputMode="decimal"
          autoFocus
          {...form.register("amount")}
          aria-invalid={!!form.formState.errors.amount}
        />
        {form.formState.errors.amount ? (
          <p className="text-destructive text-sm" role="alert">
            {form.formState.errors.amount.message}
          </p>
        ) : null}
      </div>

      <div className="space-y-2">
        <Label htmlFor="markpaid-paid-at">
          {t("payments.mark_paid_dialog.fields.received_at")}
        </Label>
        <Input
          id="markpaid-paid-at"
          type="datetime-local"
          {...form.register("paid_at")}
          aria-invalid={!!form.formState.errors.paid_at}
        />
        {form.formState.errors.paid_at ? (
          <p className="text-destructive text-sm" role="alert">
            {form.formState.errors.paid_at.message}
          </p>
        ) : null}
      </div>

      <div className="space-y-2">
        <Label htmlFor="markpaid-method">{t("payments.mark_paid_dialog.fields.method")}</Label>
        <Select value={methodCtrl.field.value} onValueChange={methodCtrl.field.onChange}>
          <SelectTrigger
            id="markpaid-method"
            aria-label={t("payments.mark_paid_dialog.fields.method")}
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {methodOptions.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <Label htmlFor="markpaid-reference">
          {t("payments.mark_paid_dialog.fields.reference")}
        </Label>
        <Input id="markpaid-reference" {...form.register("reference")} />
      </div>

      <div className="space-y-2">
        <Label htmlFor="markpaid-notes">{t("payments.mark_paid_dialog.fields.notes")}</Label>
        <Textarea id="markpaid-notes" rows={3} {...form.register("notes")} />
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
        <Button type="submit" disabled={mutation.isPending}>
          {mutation.isPending
            ? t("common:actions.saving")
            : t("payments.mark_paid_dialog.submit_label")}
        </Button>
      </div>
    </form>
  );
}

function WaiveForm({ bookingId, track, trackLabel, onOpenChange }: CommonProps) {
  const { t } = useTranslation("bookings");
  const form = useForm<WaiveTrackInput>({
    resolver: zodResolver(waiveTrackInputSchema),
    defaultValues: { reason: "" },
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  const mutation = useWaiveTrack(bookingId, track);

  const handleSubmit = async (values: WaiveTrackInput) => {
    setTopLevelError(null);
    try {
      await mutation.mutateAsync(values);
      toast.success(t("payments.waive_dialog.success_message", { track: trackLabel }));
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
    <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
      <div className="space-y-2">
        <Label htmlFor="waive-reason">{t("payments.waive_dialog.reason_label")}</Label>
        <Textarea
          id="waive-reason"
          rows={4}
          autoFocus
          {...form.register("reason")}
          aria-invalid={!!form.formState.errors.reason}
        />
        {form.formState.errors.reason ? (
          <p className="text-destructive text-sm" role="alert">
            {form.formState.errors.reason.message}
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
        <Button type="submit" disabled={mutation.isPending}>
          {mutation.isPending
            ? t("common:actions.saving")
            : t("payments.waive_dialog.submit_label")}
        </Button>
      </div>
    </form>
  );
}

export function PaymentActionDialog(props: Props) {
  const { t } = useTranslation("bookings");
  const { open, onOpenChange, action, trackLabel } = props;
  // Force re-mount of the inner form whenever the dialog re-opens so
  // useForm picks up fresh defaults (especially defaultAmount).
  const [mountKey, setMountKey] = useState(0);
  useEffect(() => {
    if (open) setMountKey((k) => k + 1);
  }, [open]);

  const title =
    action === "mark-paid"
      ? t("payments.mark_paid_dialog.title", { track: trackLabel })
      : t("payments.waive_dialog.title", { track: trackLabel });
  const description =
    action === "mark-paid"
      ? t("payments.mark_paid_dialog.description")
      : t("payments.waive_dialog.description");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        {action === "mark-paid" ? (
          <MarkPaidForm key={mountKey} {...props} />
        ) : (
          <WaiveForm key={mountKey} {...props} />
        )}
      </DialogContent>
    </Dialog>
  );
}
