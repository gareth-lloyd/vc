import { useEffect, useMemo, useState } from "react";
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
import { useQueryClient } from "@tanstack/react-query";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { ApiError } from "@/lib/api/errors";
import { queryKeys } from "@/lib/query/keys";
import { useCurrencies } from "@/features/admin/currencies/hooks";
import { createQuotationLine } from "../api";
import { useCreateGuest, useCreateQuotation, useCurrentTermsVersion } from "../hooks";
import type { QuotationDetail, QuotationLineWriteInput, StagedLine } from "../schemas";
import type { EnquiryDetail } from "@/features/enquiries/schemas";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  enquiry: EnquiryDetail | null;
  lines: StagedLine[];
  currencyCode: string;
  onCurrencyChange: (code: string) => void;
  onSaved: (quotation: QuotationDetail) => void;
}

function defaultExpiresAt(): string {
  // 7 days from now, ISO-8601 with time-of-day.
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + 7);
  d.setUTCHours(23, 59, 59, 0);
  return d.toISOString();
}

export function SaveQuoteDialog({
  open,
  onOpenChange,
  enquiry,
  lines,
  currencyCode,
  onCurrencyChange,
  onSaved,
}: Props) {
  const { t } = useTranslation("quotations");

  const currenciesQuery = useCurrencies({});
  const termsQuery = useCurrentTermsVersion();

  const [expiresAt, setExpiresAt] = useState<string>(defaultExpiresAt());
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  const qc = useQueryClient();
  const createGuest = useCreateGuest();
  const createQuotation = useCreateQuotation();
  const [linesSaving, setLinesSaving] = useState(false);
  const submitting = createGuest.isPending || createQuotation.isPending || linesSaving;

  useEffect(() => {
    if (open) {
      setExpiresAt(defaultExpiresAt());
      setTopLevelError(null);
    }
  }, [open]);

  const activeCurrencies = useMemo(
    () => (currenciesQuery.data?.results ?? []).filter((c) => c.is_active),
    [currenciesQuery.data],
  );

  const handleSubmit = async () => {
    setTopLevelError(null);
    if (!enquiry) {
      setTopLevelError(t("builder.save.errors.no_enquiry"));
      return;
    }
    if (lines.length === 0) {
      setTopLevelError(t("builder.save.errors.no_lines"));
      return;
    }
    const currency = activeCurrencies.find((c) => c.code === currencyCode);
    if (!currency) {
      setTopLevelError(t("builder.save.errors.no_currency"));
      return;
    }
    const terms = termsQuery.data;
    if (!terms) {
      setTopLevelError(t("builder.save.errors.no_terms"));
      return;
    }

    try {
      let guestId = enquiry.guest;
      if (guestId == null) {
        const guest = await createGuest.mutateAsync({
          first_name: enquiry.first_name || t("builder.save.placeholder_first_name"),
          last_name: enquiry.last_name || t("builder.save.placeholder_last_name"),
          email: enquiry.email || `enquiry-${enquiry.id}@noemail.local`,
        });
        guestId = guest.id;
      }

      const quotation = await createQuotation.mutateAsync({
        enquiry: enquiry.id,
        guest: guestId,
        agent: null,
        currency: currency.id,
        is_unbranded: false,
        expires_at: expiresAt,
        terms_version: terms.id,
      });

      setLinesSaving(true);
      try {
        await Promise.all(
          lines.map((line) => {
            const body: QuotationLineWriteInput = {
              property: line.property_id,
              date_from: line.date_from,
              date_to: line.date_to,
              adults: line.adults,
              children: line.children,
              is_manual: line.is_manual,
              notes: line.notes,
            };
            return createQuotationLine(quotation.id, body);
          }),
        );
      } finally {
        setLinesSaving(false);
      }
      qc.invalidateQueries({ queryKey: queryKeys.quotations.detail(quotation.id) });
      qc.invalidateQueries({ queryKey: queryKeys.quotations.lines(quotation.id) });

      toast.success(t("builder.save.toasts.success"));
      onSaved(quotation);
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        setTopLevelError(error.detail);
      } else {
        toast.error(t("builder.save.errors.unknown"));
      }
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !submitting && onOpenChange(o)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("builder.save.title")}</DialogTitle>
          <DialogDescription>
            {t("builder.save.description", { count: lines.length })}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="qs-currency">{t("builder.save.currency")}</Label>
            <Select value={currencyCode} onValueChange={onCurrencyChange}>
              <SelectTrigger id="qs-currency" aria-label={t("builder.save.currency")}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {activeCurrencies.map((c) => (
                  <SelectItem key={c.code} value={c.code}>
                    {c.code} — {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="qs-expires">{t("builder.save.expires_at")}</Label>
            <Input
              id="qs-expires"
              type="datetime-local"
              value={expiresAt.slice(0, 16)}
              onChange={(e) => {
                const v = e.target.value;
                setExpiresAt(v ? new Date(v).toISOString() : defaultExpiresAt());
              }}
            />
            <p className="text-muted-foreground text-xs">{t("builder.save.expires_hint")}</p>
          </div>

          <FormErrorAlert message={topLevelError} />

          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              {t("builder.save.cancel")}
            </Button>
            <Button type="button" onClick={handleSubmit} disabled={submitting}>
              {submitting ? t("builder.save.saving") : t("builder.save.confirm")}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
