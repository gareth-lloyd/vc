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
