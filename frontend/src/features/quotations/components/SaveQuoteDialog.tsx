import { useEffect, useState } from "react";
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
import { useQueryClient } from "@tanstack/react-query";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { ApiError } from "@/lib/api/errors";
import { toDecimalString } from "@/lib/format/money";
import { queryKeys } from "@/lib/query/keys";
import { createQuotationLine } from "../api";
import { useCreateGuest, useCreateQuotation, useCurrentTermsVersion } from "../hooks";
import { isStagedLineValid } from "../lineTotals";
import type { QuotationDetail, QuotationLineWriteInput, StagedLine } from "../schemas";
import type { EnquiryDetail } from "@/features/enquiries/schemas";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  enquiry: EnquiryDetail | null;
  lines: StagedLine[];
  onSaved: (quotation: QuotationDetail) => void;
}

function defaultExpiresAt(): string {
  // 7 days from now, ISO-8601 with time-of-day.
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + 7);
  d.setUTCHours(23, 59, 59, 0);
  return d.toISOString();
}

export function SaveQuoteDialog({ open, onOpenChange, enquiry, lines, onSaved }: Props) {
  const { t } = useTranslation("quotations");

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
    // Final gate before the parallel line-POST fan-out: an invalid manual line
    // (missing total/reason) would 400 mid-flight and leave a half-populated
    // quotation. The cart already blocks Save, but guard here too.
    if (!lines.every(isStagedLineValid)) {
      setTopLevelError(t("builder.save.errors.invalid_line"));
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
        // An active guest must be reachable by at least one channel (mirrors
        // the server CHECK). No synthetic email — pass through whatever the
        // enquiry actually captured; a phone-only guest is first-class valid.
        if (!enquiry.email && !enquiry.phone) {
          setTopLevelError(t("builder.save.errors.no_contact_channel"));
          return;
        }
        // Carry the enquiry's preferred channel onto the guest, but only when
        // the channel it requires was actually captured — an email preference
        // needs an email; phone/sms need a phone. Forwarding it blind would
        // trip the server's contactability CHECK (a confusing 400 at save).
        const cm = enquiry.contact_method;
        const carryContactMethod =
          (cm === "email" && enquiry.email) ||
          (cm === "phone" && enquiry.phone) ||
          (cm === "sms" && enquiry.phone)
            ? cm
            : undefined;
        const guest = await createGuest.mutateAsync({
          first_name: enquiry.first_name || t("builder.save.placeholder_first_name"),
          last_name: enquiry.last_name || t("builder.save.placeholder_last_name"),
          ...(enquiry.email ? { email: enquiry.email } : {}),
          ...(enquiry.phone ? { phone: enquiry.phone } : {}),
          ...(carryContactMethod ? { contact_method: carryContactMethod } : {}),
        });
        guestId = guest.id;
      }

      // No header currency (GAP-014) — currency lives per line.
      const quotation = await createQuotation.mutateAsync({
        enquiry: enquiry.id,
        guest: guestId,
        agent: null,
        is_unbranded: false,
        expires_at: expiresAt,
        terms_version: terms.id,
      });

      setLinesSaving(true);
      try {
        await Promise.all(
          lines.map((line) => {
            // Mirror LineEditDialog's wire shape: decimal fields can't take an
            // empty string, so `total`/`price_override_reason` ride only on the
            // manual path; the server prices non-manual lines and nets the
            // discount. Persist the operator's real per-line edits — the old
            // hardcoded `discount:"0"`/`inclusions:""` silently dropped them.
            //
            // A manual line never carries a discount: the field is disabled in
            // the cart and the server skips re-pricing manual lines, so a stale
            // discount would be stored yet never applied. Send "0" for those.
            // Otherwise normalise the typed value to a canonical 2-dp decimal
            // (`parseMoney` strips any thousands separators) so the wire always
            // gets "1000.00", never the raw "1,000" the user may have typed.
            const discount = line.is_manual ? "0" : (toDecimalString(line.discount) ?? "0");
            const body: QuotationLineWriteInput = {
              property: line.property_id,
              date_from: line.date_from,
              date_to: line.date_to,
              adults: line.adults,
              children: line.children,
              discount,
              inclusions: line.inclusions,
              is_manual: line.is_manual,
              notes: line.notes,
            };
            // Pin the currency the option was priced in (GAP-014). A line
            // without one (e.g. unpriceable) omits it so the backend resolves
            // its canonical per-property default.
            if (line.currency) {
              body.currency = line.currency;
            }
            if (line.is_manual) {
              body.total = toDecimalString(line.total) ?? "";
              body.price_override_reason = line.price_override_reason;
            }
            return createQuotationLine(quotation.id, body);
          }),
        );
      } finally {
        setLinesSaving(false);
      }
      qc.invalidateQueries({ queryKey: queryKeys.quotations.detail(quotation.id) });
      qc.invalidateQueries({ queryKey: queryKeys.quotations.lines(quotation.id) });
      // The enquiry detail carries the inline quote-stack, so a freshly-created
      // draft must refresh it (the workspace renders the new quote in place
      // without a reload). `useCreateQuotation` only invalidates the quotations
      // list/badges; the enquiry view is invalidated here, once the lines exist,
      // so the refetch sees the quote with its priced lines.
      qc.invalidateQueries({ queryKey: queryKeys.enquiries.detail(enquiry.id) });

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
