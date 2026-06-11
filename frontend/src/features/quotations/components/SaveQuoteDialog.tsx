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
import { apiErrorMessage } from "@/lib/api/forms";
import { toDatetimeLocal } from "@/lib/format/date";
import { toDecimalString } from "@/lib/format/money";
import { queryKeys } from "@/lib/query/keys";
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
  // 7 days from now at LOCAL end-of-day — expiry is local wall-clock
  // semantics; only the wire format is UTC ISO.
  const d = new Date();
  d.setDate(d.getDate() + 7);
  d.setHours(23, 59, 59, 0);
  return d.toISOString();
}

// One staged cart line → the wire shape nested under the create body's
// `lines`. `total`/`price_override_reason` ride only on the manual path
// (decimal fields can't take an empty string); the server prices non-manual
// lines and nets the discount. A manual line never carries a discount: the
// field is disabled in the cart and the server skips re-pricing manual lines,
// so a stale discount would be stored yet never applied — send "0". Money is
// normalised to canonical 2-dp decimals ("1,000" → "1000.00").
function toLineWriteBody(line: StagedLine): QuotationLineWriteInput {
  const body: QuotationLineWriteInput = {
    property: line.property_id,
    // The operator's requested dates, NOT the pre-shifted priced ones — the
    // backend is the single changeover shifter and records the move on save.
    date_from: line.date_from,
    date_to: line.date_to,
    adults: line.adults,
    children: line.children,
    discount: line.is_manual ? "0" : (toDecimalString(line.discount) ?? "0"),
    inclusions: line.inclusions,
    is_manual: line.is_manual,
    notes: line.notes,
  };
  // Pin the currency the option was priced in (GAP-014). A line without one
  // (e.g. unpriceable) omits it so the backend resolves its canonical
  // per-property default.
  if (line.currency) {
    body.currency = line.currency;
  }
  if (line.is_manual) {
    body.total = toDecimalString(line.total) ?? "";
    body.price_override_reason = line.price_override_reason;
  }
  return body;
}

export function SaveQuoteDialog({ open, onOpenChange, enquiry, lines, onSaved }: Props) {
  const { t } = useTranslation("quotations");

  const termsQuery = useCurrentTermsVersion();

  const [expiresAt, setExpiresAt] = useState<string>(defaultExpiresAt());
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  const qc = useQueryClient();
  const createGuest = useCreateGuest();
  const createQuotation = useCreateQuotation();
  // Remembers a guest created by a failed save attempt so a retry reuses it
  // instead of creating a duplicate (the enquiry cache still says `guest:
  // null` until the save succeeds and invalidates it).
  const [createdGuestId, setCreatedGuestId] = useState<number | null>(null);
  const submitting = createGuest.isPending || createQuotation.isPending;

  useEffect(() => {
    if (open) {
      setExpiresAt(defaultExpiresAt());
      setTopLevelError(null);
      setCreatedGuestId(null);
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
    // The save is atomic server-side, so an invalid line can no longer leave
    // a half-populated quotation — this gate is pure UX: an instant banner
    // instead of a round-trip 400. The cart already blocks Save; guard again.
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
      let guestId = enquiry.guest ?? createdGuestId;
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
        setCreatedGuestId(guest.id);
        guestId = guest.id;
      }

      // One atomic POST: header + lines + pricing + holds succeed or fail
      // together server-side — never a half-populated draft. No header
      // currency (GAP-014) — currency lives per line.
      const quotation = await createQuotation.mutateAsync({
        enquiry: enquiry.id,
        guest: guestId,
        agent: null,
        is_unbranded: false,
        expires_at: expiresAt,
        terms_version: terms.id,
        lines: lines.map(toLineWriteBody),
      });

      // The enquiry detail carries the inline quote-stack, so a freshly-created
      // draft must refresh it (the workspace renders the new quote in place
      // without a reload). `useCreateQuotation` already invalidates the
      // quotations list/badges; the brand-new detail has no cached entries.
      qc.invalidateQueries({ queryKey: queryKeys.enquiries.detail(enquiry.id) });

      toast.success(t("builder.save.toasts.success"));
      onSaved(quotation);
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        // Include nested per-line messages — the bare detail for a nested 400
        // is just "Validation failed".
        setTopLevelError(apiErrorMessage(error));
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
              value={toDatetimeLocal(expiresAt)}
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
