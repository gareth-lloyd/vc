// Neutral home for cross-feature domain schemas (GAP-063; GAP-062's shared
// money/country schemas land here too). The quotation read-model lives here
// because enquiries embeds quotations in its detail payload — importing it
// from features/quotations would recreate the enquiries⇄quotations cycle.
// features/quotations/schemas.ts re-exports everything for intra-feature use.
import { z } from "zod";
import i18n from "@/i18n";

export const quotationStatusSchema = z.enum(["draft", "sent", "accepted", "expired", "cancelled"]);
export type QuotationStatus = z.infer<typeof quotationStatusSchema>;

// Accepts plain strings because detail/list payloads keep `status` loose
// (the backend's TextChoices may grow); unknown values render verbatim.
export function quotationStatusLabel(status: QuotationStatus | string): string {
  return i18n.t(`quotations:labels.status.${status}`, { defaultValue: status });
}

// `status` is permissive — backend's TextChoices may grow and we don't want
// to crash the list page if a new value shows up.
const looseStatus = z.string();

export const quotationListItemSchema = z.object({
  id: z.number(),
  reference: z.string(),
  enquiry: z.number().nullable().optional(),
  enquiry_reference: z.string().nullable().optional(),
  guest: z.number().nullable().optional(),
  guest_name: z.string().nullable().optional(),
  agent: z.number().nullable().optional(),
  agent_name: z.string().nullable().optional(),
  status: looseStatus,
  expires_at: z.string().nullable().optional(),
  is_unbranded: z.boolean().optional().default(false),
  terms_version: z.number().nullable().optional(),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
});
export type QuotationListItem = z.infer<typeof quotationListItemSchema>;

export const quotationLineSchema = z.object({
  id: z.number(),
  quotation: z.number().optional(),
  property: z.number().nullable().optional(),
  property_name: z.string().nullable().optional(),
  hero_image_url: z.string().nullable().optional(),
  date_from: z.string().nullable().optional(),
  date_to: z.string().nullable().optional(),
  // The original arrival when the engine nudged it forward to the property's
  // changeover day (GAP-007). Null/absent when the dates weren't moved.
  changeover_shifted_from: z.string().nullable().optional(),
  // The line's live manual hold, or null. Holds are a deliberate operator
  // action (:hold / :release-hold) — never a side effect of quoting.
  hold: z
    .object({
      id: z.number(),
      date_from: z.string().nullable().optional(),
      date_to: z.string().nullable().optional(),
      expires_at: z.string().nullable().optional(),
    })
    .nullable()
    .optional(),
  adults: z.number().optional().default(0),
  children: z.number().optional().default(0),
  // ISO code the line was priced in (GAP-014) — currency lives per line, not
  // on the quotation header; a mixed-currency quote is legacy-parity.
  currency: z.string().nullable().optional(),
  pricing_snapshot: z.unknown().optional(),
  total: z.union([z.string(), z.number()]).nullable().optional(),
  discount: z.union([z.string(), z.number()]).nullable().optional(),
  inclusions: z.string().optional().default(""),
  price_override_reason: z.string().optional().default(""),
  is_selected: z.boolean().optional().default(false),
  is_manual: z.boolean().optional().default(false),
  notes: z.string().optional().default(""),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
});
export type QuotationLine = z.infer<typeof quotationLineSchema>;

export const quotationDetailSchema = quotationListItemSchema.extend({
  cancel_reason: z.string().optional().default(""),
  lines: z.array(quotationLineSchema).optional().default([]),
});
export type QuotationDetail = z.infer<typeof quotationDetailSchema>;
