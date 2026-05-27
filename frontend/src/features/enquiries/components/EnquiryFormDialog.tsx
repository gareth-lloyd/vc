import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useController, useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Minus, Plus } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
import { applyApiErrorToForm } from "@/lib/api/forms";
import { ApiError } from "@/lib/api/errors";
import { useCreateEnquiry, useUpdateEnquiry } from "../hooks";
import {
  enquirySourceOptions,
  enquiryRequestTypeOptions,
  enquiryWriteInputSchema,
  type EnquiryDetail,
  type EnquiryWriteInput,
} from "../schemas";

interface CommonProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface CreateProps extends CommonProps {
  mode: "create";
}

interface EditProps extends CommonProps {
  mode: "edit";
  enquiry: EnquiryDetail;
}

type EnquiryFormDialogProps = CreateProps | EditProps;

const MIN_SPREAD = 0;
const MAX_SPREAD = 3;

// Shift an ISO `YYYY-MM-DD` date by `delta` days. Returns the original string
// when it isn't parseable so we never mangle empty fields.
function shiftIsoDate(iso: string, delta: number): string {
  if (!iso || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return iso;
  const [year, month, day] = iso.split("-").map((n) => Number.parseInt(n, 10));
  // Use UTC to avoid local-tz boundary surprises on day arithmetic.
  const ms = Date.UTC(year, month - 1, day) + delta * 24 * 60 * 60 * 1000;
  const d = new Date(ms);
  const yyyy = d.getUTCFullYear().toString().padStart(4, "0");
  const mm = (d.getUTCMonth() + 1).toString().padStart(2, "0");
  const dd = d.getUTCDate().toString().padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

const CREATE_DEFAULTS: EnquiryWriteInput = {
  first_name: "",
  last_name: "",
  email: "",
  phone: "",
  date_from: "",
  date_to: "",
  is_flexible: false,
  adults: 2,
  children: 0,
  min_bedrooms: null,
  request_type: "quote",
  site_source: "main_website",
  inbound_message: "",
};

function defaultsFromEnquiry(enq: EnquiryDetail): EnquiryWriteInput {
  return {
    first_name: enq.first_name ?? "",
    last_name: enq.last_name ?? "",
    email: enq.email ?? "",
    phone: "",
    date_from: enq.date_from ?? "",
    date_to: enq.date_to ?? "",
    is_flexible: enq.is_flexible ?? false,
    adults: enq.adults,
    children: enq.children ?? 0,
    min_bedrooms: enq.min_bedrooms ?? null,
    request_type: enq.request_type,
    site_source: enq.site_source,
    inbound_message: enq.inbound_message ?? "",
  };
}

export function EnquiryFormDialog(props: EnquiryFormDialogProps) {
  const { t } = useTranslation("enquiries");
  const { open, onOpenChange } = props;
  const isCreate = props.mode === "create";

  const form = useForm<EnquiryWriteInput>({
    resolver: zodResolver(enquiryWriteInputSchema),
    defaultValues: isCreate ? CREATE_DEFAULTS : defaultsFromEnquiry(props.enquiry),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  // Operator convention: widen the captured date range by ±N days around the
  // client's requested dates. See enquiry-intake.md "Django redesign —
  // date-spread heuristic". Local-only UI state; submitted as the resolved
  // `date_from` / `date_to` on the existing fields.
  const [spread, setSpread] = useState<number>(MIN_SPREAD);

  const createMutation = useCreateEnquiry();
  const updateMutation = useUpdateEnquiry(isCreate ? 0 : props.enquiry.id);
  const submitting = createMutation.isPending || updateMutation.isPending;

  useEffect(() => {
    if (open) {
      form.reset(isCreate ? CREATE_DEFAULTS : defaultsFromEnquiry(props.enquiry));
      setTopLevelError(null);
      setSpread(MIN_SPREAD);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? null : props.enquiry.id]);

  const requestTypeCtrl = useController({ control: form.control, name: "request_type" });
  const sourceCtrl = useController({ control: form.control, name: "site_source" });
  const flexibleCtrl = useController({ control: form.control, name: "is_flexible" });

  // Watch the typed dates so the widened preview updates as the operator types.
  const requestedFrom = useWatch({ control: form.control, name: "date_from" }) ?? "";
  const requestedTo = useWatch({ control: form.control, name: "date_to" }) ?? "";
  const widened = useMemo(() => {
    const from = requestedFrom ? shiftIsoDate(requestedFrom, -spread) : "";
    const to = requestedTo ? shiftIsoDate(requestedTo, spread) : "";
    return { from, to };
  }, [requestedFrom, requestedTo, spread]);

  const idleSubmitLabel = isCreate ? t("common:actions.create") : t("common:actions.save");

  const handleSubmit = async (values: EnquiryWriteInput) => {
    setTopLevelError(null);
    const submitted: EnquiryWriteInput = {
      ...values,
      date_from: values.date_from ? shiftIsoDate(values.date_from, -spread) : values.date_from,
      date_to: values.date_to ? shiftIsoDate(values.date_to, spread) : values.date_to,
    };
    try {
      if (isCreate) {
        await createMutation.mutateAsync(submitted);
      } else {
        await updateMutation.mutateAsync(submitted);
      }
      toast.success(isCreate ? t("form_dialog.toasts.created") : t("form_dialog.toasts.updated"));
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
            {isCreate ? t("form_dialog.titles.create") : t("form_dialog.titles.edit")}
          </DialogTitle>
          <DialogDescription>{t("form_dialog.description")}</DialogDescription>
        </DialogHeader>

        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="enq-first-name">{t("form_dialog.fields.first_name")}</Label>
              <Input id="enq-first-name" {...form.register("first_name")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="enq-last-name">{t("form_dialog.fields.last_name")}</Label>
              <Input id="enq-last-name" {...form.register("last_name")} />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="enq-email">{t("form_dialog.fields.email")}</Label>
            <Input
              id="enq-email"
              type="email"
              {...form.register("email")}
              aria-invalid={!!form.formState.errors.email}
            />
            {form.formState.errors.email ? (
              <p className="text-destructive text-sm" role="alert">
                {form.formState.errors.email.message}
              </p>
            ) : null}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="enq-date-from">{t("form_dialog.fields.from")}</Label>
              <Input id="enq-date-from" type="date" {...form.register("date_from")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="enq-date-to">{t("form_dialog.fields.to")}</Label>
              <Input id="enq-date-to" type="date" {...form.register("date_to")} />
            </div>
          </div>

          <div className="space-y-1">
            <div className="flex items-center gap-3">
              <span className="text-sm font-medium">{t("form_dialog.date_spread.label")}</span>
              <div className="flex items-center gap-1">
                <Button
                  type="button"
                  variant="outline"
                  size="icon-sm"
                  aria-label={t("form_dialog.date_spread.decrease_aria")}
                  disabled={spread <= MIN_SPREAD}
                  onClick={() => setSpread((s) => Math.max(MIN_SPREAD, s - 1))}
                >
                  <Minus className="h-3 w-3" />
                </Button>
                <span
                  className="min-w-[4.5rem] text-center text-sm tabular-nums"
                  aria-live="polite"
                >
                  {t("form_dialog.date_spread.value", { count: spread })}
                </span>
                <Button
                  type="button"
                  variant="outline"
                  size="icon-sm"
                  aria-label={t("form_dialog.date_spread.increase_aria")}
                  disabled={spread >= MAX_SPREAD}
                  onClick={() => setSpread((s) => Math.min(MAX_SPREAD, s + 1))}
                >
                  <Plus className="h-3 w-3" />
                </Button>
              </div>
            </div>
            <p className="text-muted-foreground text-xs">
              {spread === 0 || !widened.from || !widened.to
                ? t("form_dialog.date_spread.hint")
                : t("form_dialog.date_spread.preview_widened", {
                    from: widened.from,
                    to: widened.to,
                  })}
            </p>
          </div>

          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <Checkbox
              checked={!!flexibleCtrl.field.value}
              onCheckedChange={(v) => flexibleCtrl.field.onChange(v === true)}
            />
            <span>{t("form_dialog.fields.flexible_dates")}</span>
          </label>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="enq-adults">{t("form_dialog.fields.adults")}</Label>
              <Input
                id="enq-adults"
                type="number"
                min={1}
                {...form.register("adults", { valueAsNumber: true })}
                aria-invalid={!!form.formState.errors.adults}
              />
              {form.formState.errors.adults ? (
                <p className="text-destructive text-sm" role="alert">
                  {form.formState.errors.adults.message}
                </p>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="enq-children">{t("form_dialog.fields.children")}</Label>
              <Input
                id="enq-children"
                type="number"
                min={0}
                {...form.register("children", { valueAsNumber: true })}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="enq-request-type">{t("form_dialog.fields.request_type")}</Label>
              <Select
                value={requestTypeCtrl.field.value}
                onValueChange={requestTypeCtrl.field.onChange}
              >
                <SelectTrigger
                  id="enq-request-type"
                  aria-label={t("form_dialog.fields.request_type_aria")}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {enquiryRequestTypeOptions().map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="enq-source">{t("form_dialog.fields.source")}</Label>
              <Select value={sourceCtrl.field.value} onValueChange={sourceCtrl.field.onChange}>
                <SelectTrigger id="enq-source" aria-label={t("form_dialog.fields.source_aria")}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {enquirySourceOptions().map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="enq-message">{t("form_dialog.fields.inbound_message")}</Label>
            <Textarea id="enq-message" rows={3} {...form.register("inbound_message")} />
          </div>

          {topLevelError ? (
            <div
              className="bg-destructive/10 text-destructive border-destructive/40 rounded-md border p-3 text-sm"
              role="alert"
            >
              {topLevelError}
            </div>
          ) : null}

          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
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
