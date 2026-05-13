import { z } from "zod";
import { paginated } from "@/lib/api/pagination";

export const quotationStatusSchema = z.enum(["draft", "sent", "accepted", "expired", "cancelled"]);
export type QuotationStatus = z.infer<typeof quotationStatusSchema>;

export const QUOTATION_STATUS_LABELS: Record<QuotationStatus, string> = {
  draft: "Draft",
  sent: "Sent",
  accepted: "Accepted",
  expired: "Expired",
  cancelled: "Cancelled",
};

export const QUOTATION_STATUS_OPTIONS = quotationStatusSchema.options.map((value) => ({
  value,
  label: QUOTATION_STATUS_LABELS[value],
}));

// `status` is permissive — backend's TextChoices may grow and we don't want
// to crash the list page if a new value shows up.
const looseStatus = z.string();

export const quotationListItemSchema = z.object({
  id: z.number(),
  reference: z.string(),
  enquiry: z.number().nullable().optional(),
  guest: z.number().nullable().optional(),
  agent: z.number().nullable().optional(),
  currency: z.string().nullable().optional(),
  status: looseStatus,
  expires_at: z.string().nullable().optional(),
  is_unbranded: z.boolean().optional().default(false),
  terms_version: z.string().optional().default(""),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
});
export type QuotationListItem = z.infer<typeof quotationListItemSchema>;

export const quotationLineSchema = z.object({
  id: z.number(),
  quotation: z.number().optional(),
  property: z.number().nullable().optional(),
  date_from: z.string().nullable().optional(),
  date_to: z.string().nullable().optional(),
  adults: z.number().optional().default(0),
  children: z.number().optional().default(0),
  pricing_snapshot: z.unknown().optional(),
  total: z.union([z.string(), z.number()]).nullable().optional(),
  is_selected: z.boolean().optional().default(false),
  is_manual: z.boolean().optional().default(false),
  notes: z.string().optional().default(""),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
});
export type QuotationLine = z.infer<typeof quotationLineSchema>;

// ----------------------------------------------------------------------
// Quote builder schemas — criteria, search results, save payload.
// ----------------------------------------------------------------------

export const quoteCriteriaInputSchema = z
  .object({
    date_from: z.string().min(1, "Required"),
    date_to: z.string().min(1, "Required"),
    adults: z.number().int().min(1, "At least one adult"),
    children: z.number().int().min(0),
    country: z.string(),
    region: z.string(),
    min_bedrooms: z.number().int().min(0).nullable(),
    max_bedrooms: z.number().int().min(0).nullable(),
    q: z.string(),
  })
  .refine((v) => !v.date_from || !v.date_to || v.date_from < v.date_to, {
    path: ["date_to"],
    message: "Must be after the start date",
  });
export type QuoteCriteriaInput = z.infer<typeof quoteCriteriaInputSchema>;

// One priced result row returned from the builder search. The server
// pricing breakdown is opaque — we surface only the headline total +
// any error code, the rest stays in the snapshot for line save.
export const quoteOptionSchema = z.object({
  property_id: z.number(),
  property_name: z.string(),
  property_slug: z.string().nullable().optional(),
  available: z.boolean(),
  total: z.union([z.string(), z.number()]).nullable().optional(),
  currency: z.string().nullable().optional(),
  rate_subtotal: z.union([z.string(), z.number()]).nullable().optional(),
  nights: z.number().optional(),
  error_code: z.string().nullable().optional(),
  error_detail: z.string().nullable().optional(),
  breakdown: z.unknown().optional(),
});
export type QuoteOption = z.infer<typeof quoteOptionSchema>;

// One row in the operator-staged "lines so far" panel. Pre-save shape.
// `is_selected` is intentionally absent — the backend sets it during the
// `accept()` transition (convert-to-booking), not at create time.
export interface StagedLine {
  property_id: number;
  property_name: string;
  date_from: string;
  date_to: string;
  adults: number;
  children: number;
  total: string | number | null;
  is_manual: boolean;
  notes: string;
}

// Header write — what `POST /quotations` accepts.
export const quotationWriteInputSchema = z.object({
  enquiry: z.number().int().nullable(),
  guest: z.number().int(),
  agent: z.number().int().nullable().optional(),
  currency: z.number().int(),
  is_unbranded: z.boolean().optional().default(false),
  expires_at: z.string(),
  terms_version: z.number().int(),
});
export type QuotationWriteInput = z.infer<typeof quotationWriteInputSchema>;

// Line write — what `POST /quotations/{id}/lines` accepts.
export const quotationLineWriteInputSchema = z.object({
  property: z.number().int(),
  date_from: z.string().min(1),
  date_to: z.string().min(1),
  adults: z.number().int().min(1),
  children: z.number().int().min(0),
  is_manual: z.boolean().optional().default(false),
  notes: z.string().optional().default(""),
});
export type QuotationLineWriteInput = z.infer<typeof quotationLineWriteInputSchema>;

// Current terms version — returned by GET /terms-versions/current.
export const termsVersionSchema = z.object({
  id: z.number(),
  version: z.string(),
  is_current: z.boolean(),
  published_at: z.string().nullable().optional(),
});
export type TermsVersion = z.infer<typeof termsVersionSchema>;

// Minimal guest shape returned by POST /guests.
export const guestSchema = z.object({
  id: z.number(),
  first_name: z.string(),
  last_name: z.string(),
  email: z.string(),
});
export type GuestSummary = z.infer<typeof guestSchema>;

export const quotationDetailSchema = quotationListItemSchema.extend({
  cancel_reason: z.string().optional().default(""),
  lines: z.array(quotationLineSchema).optional().default([]),
});
export type QuotationDetail = z.infer<typeof quotationDetailSchema>;

export const quotationListResponseSchema = paginated(quotationListItemSchema);

// Lines endpoint is a nested router viewset — paginated like everything else.
export const quotationLinesResponseSchema = paginated(quotationLineSchema);

export interface QuotationFilters {
  q?: string;
  status?: string;
  enquiry?: number;
  guest?: number;
  ordering?: string;
  page?: number;
}
