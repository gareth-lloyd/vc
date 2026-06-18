import { z } from "zod";
import i18n from "@/i18n";
import { paginated } from "@/lib/api/pagination";
import { quotationDetailSchema } from "@/features/quotations/schemas";

export const enquiryStatusSchema = z.enum([
  "new",
  "progressing",
  "quote_sent",
  "dead",
  "converted",
]);
export type EnquiryStatus = z.infer<typeof enquiryStatusSchema>;

// Columns shown on the Kanban board. Both `dead` and `progressing` are excluded:
// `dead` is reachable via Close, but `progressing` has no forward affordance in the
// app (nothing calls Enquiry.contact(); it only arrives via the legacy data
// migration). The board therefore shows the funnel operators can actually drive —
// new → quote_sent → converted. Either excluded status is still filterable in the
// list view.
export const KANBAN_STATUSES: readonly EnquiryStatus[] = [
  "new",
  "quote_sent",
  "converted",
] as const;

export const enquirySourceSchema = z.enum([
  "main_website",
  "agent_portal",
  "email_inbound",
  "phone",
  "other",
]);
export type EnquirySource = z.infer<typeof enquirySourceSchema>;

export const enquiryRequestTypeSchema = z.enum([
  "availability",
  "info",
  "quote",
  "brochure",
  "other",
]);
export type EnquiryRequestType = z.infer<typeof enquiryRequestTypeSchema>;

export const contactMethodSchema = z.enum(["email", "phone", "sms"]);
export type ContactMethod = z.infer<typeof contactMethodSchema>;

export const enquiryListItemSchema = z.object({
  id: z.number(),
  reference: z.string(),
  status: enquiryStatusSchema,
  guest: z.number().nullable().optional(),
  guest_name: z.string().nullable().optional(),
  // Read-only contact details sourced from the linked Guest — the
  // denormalised email/phone/contact_method below are blank for
  // guest-linked enquiries.
  guest_email: z.string().nullable().optional(),
  guest_phone: z.string().nullable().optional(),
  guest_contact_method: contactMethodSchema.nullable().optional(),
  first_name: z.string().optional().default(""),
  last_name: z.string().optional().default(""),
  email: z.string().optional().default(""),
  phone: z.string().optional().default(""),
  contact_method: contactMethodSchema.nullable().optional(),
  property: z.number().nullable().optional(),
  property_name: z.string().nullable().optional(),
  region: z.number().nullable().optional(),
  region_name: z.string().nullable().optional(),
  date_from: z.string().nullable().optional(),
  date_to: z.string().nullable().optional(),
  adults: z.number(),
  children: z.number().default(0),
  request_type: enquiryRequestTypeSchema,
  assigned_to: z.number().nullable().optional(),
  assigned_to_name: z.string().nullable().optional(),
  agent: z.number().nullable().optional(),
  agent_name: z.string().nullable().optional(),
  site_source: enquirySourceSchema,
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
});
export type EnquiryListItem = z.infer<typeof enquiryListItemSchema>;

export const enquiryDetailSchema = enquiryListItemSchema.extend({
  is_flexible: z.boolean().optional().default(false),
  // Structured "± N days" spread; dates stay the client's true requested
  // dates and the quote search widens by this value.
  flexibility_days: z.number().int().optional().default(0),
  min_bedrooms: z.number().nullable().optional(),
  referral_code: z.string().optional().default(""),
  inbound_message: z.string().optional().default(""),
  // The full quote-stack the merged workspace renders inline. The backend
  // already excludes `booking-` synthetic rows (see `Quotation.objects.real()`).
  quotations: z.array(quotationDetailSchema).optional().default([]),
});
export type EnquiryDetail = z.infer<typeof enquiryDetailSchema>;

/** Display name for an enquiry: linked-guest name, then the denormalised
 * lead-capture name, then email, then the reference as a last resort. */
export function guestName(enq: EnquiryDetail): string {
  if (enq.guest_name) return enq.guest_name;
  const denorm = `${enq.first_name ?? ""} ${enq.last_name ?? ""}`.trim();
  return denorm || enq.email || enq.reference;
}

export const enquiryListResponseSchema = paginated(enquiryListItemSchema);

export const enquiryEventKindSchema = z.enum([
  "status_change",
  "assigned",
  "unassigned",
  "contacted",
  "quote_sent",
  "converted",
  "lost",
  "reopened",
  "note_added",
]);
export type EnquiryEventKind = z.infer<typeof enquiryEventKindSchema>;

export const enquiryActivitySchema = z.object({
  id: z.number(),
  enquiry: z.number().optional(),
  from_status: z.string().nullable(),
  to_status: z.string(),
  kind: z.string(),
  actor: z.number().nullable().optional(),
  source: z.string(),
  reason: z.string().optional().default(""),
  meta: z.record(z.string(), z.unknown()).optional().default({}),
  created_at: z.string(),
});
export type EnquiryActivity = z.infer<typeof enquiryActivitySchema>;

// The backend activity endpoint returns a plain array (not paginated).
export const enquiryActivityResponseSchema = z.array(enquiryActivitySchema);

export const enquiryNoteKindSchema = z.enum(["general", "internal", "preferences"]);
export type EnquiryNoteKind = z.infer<typeof enquiryNoteKindSchema>;

export const enquiryNoteSchema = z.object({
  id: z.number(),
  enquiry: z.number().optional(),
  author: z.number().nullable().optional(),
  kind: enquiryNoteKindSchema,
  body: z.string(),
  is_pinned: z.boolean().optional().default(false),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
});
export type EnquiryNote = z.infer<typeof enquiryNoteSchema>;

export const enquiryNotesResponseSchema = paginated(enquiryNoteSchema);

export const enquiryNoteWriteInputSchema = z.object({
  kind: enquiryNoteKindSchema,
  body: z.string().trim().min(1, i18n.t("enquiries:schema_errors.body_required")).max(10_000),
  is_pinned: z.boolean(),
});
export type EnquiryNoteWriteInput = z.infer<typeof enquiryNoteWriteInputSchema>;

export const enquiryWriteInputSchema = z
  .object({
    // Resolved guest link (existing-client picker). Null = free-text capture /
    // create-new; the backend mints or reuses the Guest from the denorm fields.
    guest: z.number().nullable(),
    first_name: z.string().trim().max(128),
    last_name: z.string().trim().max(128),
    email: z
      .string()
      .trim()
      .refine((v) => v === "" || /.+@.+\..+/.test(v), {
        message: i18n.t("common:zod.invalid_email"),
      }),
    phone: z.string().trim().max(32),
    date_from: z.string().nullable(),
    date_to: z.string().nullable(),
    is_flexible: z.boolean(),
    flexibility_days: z.number().int().min(0).max(3),
    adults: z.number().int().min(1, i18n.t("enquiries:schema_errors.at_least_one_adult")),
    children: z.number().int().min(0),
    min_bedrooms: z.number().int().min(0).nullable(),
    request_type: enquiryRequestTypeSchema,
    contact_method: contactMethodSchema.nullable(),
    site_source: enquirySourceSchema,
    inbound_message: z.string().trim().max(10_000),
  })
  // Dates are an optional, independent capture surface (a lead may have a
  // start, an end, both, or neither), so the only cross-field rule is: when
  // both ends are set, the end must not precede the start. ISO YYYY-MM-DD
  // strings compare chronologically as plain strings. The issue is pinned to
  // `date_to` so it renders beside the end-date input.
  .superRefine((val, ctx) => {
    if (val.date_from && val.date_to && val.date_to < val.date_from) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["date_to"],
        message: i18n.t("enquiries:schema_errors.date_to_before_from"),
      });
    }
  });
export type EnquiryWriteInput = z.infer<typeof enquiryWriteInputSchema>;

export const assignEnquiryInputSchema = z.object({
  user: z.number().int().nullable(),
});
export type AssignEnquiryInput = z.infer<typeof assignEnquiryInputSchema>;

export const closeEnquiryInputSchema = z.object({
  reason: z.string().trim().max(255).optional().default(""),
});
export type CloseEnquiryInput = z.infer<typeof closeEnquiryInputSchema>;

export interface EnquiryFilters {
  q?: string;
  status?: EnquiryStatus;
  site_source?: EnquirySource;
  ordering?: string;
  page?: number;
}

// A "final" enquiry (dead or converted) is closed to new quotes: the workspace
// suppresses the inline builder and the close action is disabled for these.
export function isFinalStatus(status: EnquiryStatus): boolean {
  return status === "converted" || status === "dead";
}

export function enquiryStatusLabel(status: EnquiryStatus): string {
  return i18n.t(`enquiries:labels.status.${status}`);
}

export function enquirySourceLabel(source: EnquirySource): string {
  return i18n.t(`enquiries:labels.source.${source}`);
}

export function enquiryNoteKindLabel(kind: EnquiryNoteKind): string {
  return i18n.t(`enquiries:labels.note_kind.${kind}`);
}

export function enquiryRequestTypeLabel(value: EnquiryRequestType): string {
  return i18n.t(`enquiries:labels.request_type.${value}`);
}

export function contactMethodLabel(value: ContactMethod): string {
  return i18n.t(`enquiries:labels.contact_method.${value}`);
}

export const enquiryStatusOptions = (): Array<{ value: EnquiryStatus; label: string }> =>
  enquiryStatusSchema.options.map((value) => ({ value, label: enquiryStatusLabel(value) }));

export const enquirySourceOptions = (): Array<{ value: EnquirySource; label: string }> =>
  enquirySourceSchema.options.map((value) => ({ value, label: enquirySourceLabel(value) }));

export const enquiryNoteKindOptions = (): Array<{ value: EnquiryNoteKind; label: string }> =>
  enquiryNoteKindSchema.options.map((value) => ({ value, label: enquiryNoteKindLabel(value) }));

export const enquiryRequestTypeOptions = (): Array<{
  value: EnquiryRequestType;
  label: string;
}> =>
  enquiryRequestTypeSchema.options.map((value) => ({
    value,
    label: enquiryRequestTypeLabel(value),
  }));

export const contactMethodOptions = (): Array<{ value: ContactMethod; label: string }> =>
  contactMethodSchema.options.map((value) => ({ value, label: contactMethodLabel(value) }));
