import { z } from "zod";
import i18n from "@/i18n";
import { paginated } from "@/lib/api/pagination";
import { bookingStatusSchema } from "@/features/bookings/schemas";
import { enquiryStatusSchema } from "@/features/enquiries/schemas";

export const contactEmailSchema = z.object({
  id: z.number(),
  email: z.string(),
  label: z.string().nullable().optional(),
  is_primary: z.boolean().optional(),
});
export type ContactEmail = z.infer<typeof contactEmailSchema>;

export const contactPhoneSchema = z.object({
  id: z.number(),
  number: z.string(),
  label: z.string().nullable().optional(),
  is_primary: z.boolean().optional(),
});
export type ContactPhone = z.infer<typeof contactPhoneSchema>;

export const contactEmailWriteInputSchema = z.object({
  email: z.string().email(i18n.t("common:zod.invalid_email")).max(254),
  label: z.string().trim().max(40).optional(),
  is_primary: z.boolean().optional(),
});
export type ContactEmailWriteInput = z.infer<typeof contactEmailWriteInputSchema>;

export const contactPhoneWriteInputSchema = z.object({
  number: z.string().trim().min(1, i18n.t("common:errors.field_required")).max(40),
  label: z.string().trim().max(40).optional(),
  is_primary: z.boolean().optional(),
});
export type ContactPhoneWriteInput = z.infer<typeof contactPhoneWriteInputSchema>;

export const contactWriteInputSchema = z
  .object({
    title: z.string().trim().max(40).optional(),
    first_name: z.string().trim().max(80).optional(),
    last_name: z.string().trim().max(80).optional(),
    company: z.string().trim().max(160).optional(),
    website_url: z.string().trim().max(255).optional(),
    preferred_method: z.string().trim().max(40).optional(),
    address_line_1: z.string().trim().max(255).optional(),
    address_line_2: z.string().trim().max(255).optional(),
    notes: z.string().trim().max(2000).optional(),
  })
  .refine((v) => v.first_name || v.last_name || v.company, {
    message: i18n.t("contacts:errors.name_or_company_required"),
    path: ["first_name"],
  });
export type ContactWriteInput = z.infer<typeof contactWriteInputSchema>;

// Create form schema: the base write fields plus a single email/phone field, so
// a new active contact arrives reachable (the backend rejects an active contact
// with no channel). The dialog folds the single fields into the inline
// `emails`/`phones` arrays the API expects (see `ContactCreateBody`).
export const contactCreateInputSchema = z
  .object({
    title: z.string().trim().max(40).optional(),
    first_name: z.string().trim().max(80).optional(),
    last_name: z.string().trim().max(80).optional(),
    company: z.string().trim().max(160).optional(),
    website_url: z.string().trim().max(255).optional(),
    preferred_method: z.string().trim().max(40).optional(),
    address_line_1: z.string().trim().max(255).optional(),
    address_line_2: z.string().trim().max(255).optional(),
    notes: z.string().trim().max(2000).optional(),
    email: z
      .string()
      .trim()
      .max(254)
      .optional()
      .refine((v) => !v || z.string().email().safeParse(v).success, {
        message: i18n.t("common:zod.invalid_email"),
      }),
    phone: z.string().trim().max(40).optional(),
  })
  .refine((v) => v.first_name || v.last_name || v.company, {
    message: i18n.t("contacts:errors.name_or_company_required"),
    path: ["first_name"],
  })
  .refine((v) => Boolean(v.email || v.phone), {
    message: i18n.t("contacts:errors.channel_required"),
    path: ["email"],
  });
export type ContactCreateInput = z.infer<typeof contactCreateInputSchema>;

// Wire shape POSTed to /contacts: base write fields + inline channel arrays.
// `kind` is accepted create-only (GAP-045 D2) — the quote builder sends
// `kind: "customer"` to mint a customer Person; the contacts form omits it so
// the backend defaults to CONTACT.
export type ContactCreateBody = ContactWriteInput & {
  kind?: "contact" | "customer";
  emails?: ContactEmailWriteInput[];
  phones?: ContactPhoneWriteInput[];
};

export const contactSchema = z.object({
  id: z.number(),
  title: z.string().nullable().optional(),
  first_name: z.string().nullable().optional(),
  last_name: z.string().nullable().optional(),
  company: z.string().nullable().optional(),
  website_url: z.string().nullable().optional(),
  preferred_method: z.string().nullable().optional(),
  address_line_1: z.string().nullable().optional(),
  address_line_2: z.string().nullable().optional(),
  notes: z.string().nullable().optional(),
  status: z.string().nullable().optional(),
  emails: z.array(contactEmailSchema).optional().default([]),
  phones: z.array(contactPhoneSchema).optional().default([]),
});
export type Contact = z.infer<typeof contactSchema>;

export const contactPropertyAssignmentSchema = z.object({
  id: z.number(),
  property_id: z.number(),
  property_slug: z.string().nullable().optional(),
  role: z.string().nullable().optional(),
  is_primary: z.boolean().optional(),
  start_date: z.string().nullable().optional(),
  end_date: z.string().nullable().optional(),
});
export type ContactPropertyAssignment = z.infer<typeof contactPropertyAssignmentSchema>;

export const contactListItemSchema = z.object({
  id: z.number(),
  title: z.string().nullable().optional(),
  first_name: z.string().nullable().optional(),
  last_name: z.string().nullable().optional(),
  company: z.string().nullable().optional(),
  status: z.string().nullable().optional(),
  // GAP-045 D2: CUSTOMER (was Guest) vs CONTACT (owner/manager/agent) — drives
  // the directory's kind filter + column.
  kind: z.string().nullable().optional(),
  // The backend returns the full ContactSerializer shape for list responses,
  // so emails/phones come through as arrays. We accept the convenience
  // `primary_email` / `primary_phone` strings too in case the list serializer
  // is later trimmed.
  primary_email: z.string().nullable().optional(),
  primary_phone: z.string().nullable().optional(),
  emails: z.array(contactEmailSchema).optional().default([]),
  phones: z.array(contactPhoneSchema).optional().default([]),
});
export type ContactListItem = z.infer<typeof contactListItemSchema>;

export const contactsListResponseSchema = paginated(contactListItemSchema);

export interface ContactFilters {
  q?: string;
  status?: string;
  kind?: string;
  ordering?: string;
  page?: number;
}

export const contactListFiltersSchema = z.object({
  q: z.string().optional(),
  status: z.string().optional(),
  kind: z.string().optional(),
  ordering: z.string().optional(),
  page: z.number().optional(),
});

// `/contacts/{id}/enquiries` returns the SAME shape as `/guests/{id}/enquiries`
// (GAP-045 D2). Contacts owns its own copy of the schema so D4 can delete the
// guests module without breaking the enquiry surface.
export const contactConvertedBookingSchema = z.object({
  reference: z.string(),
  status: bookingStatusSchema,
});
export type ContactConvertedBooking = z.infer<typeof contactConvertedBookingSchema>;

export const contactEnquiryHistorySchema = z.object({
  id: z.number(),
  reference: z.string(),
  status: enquiryStatusSchema,
  site_source: z.string().nullable().optional(),
  request_type: z.string().nullable().optional(),
  created_at: z.string().nullable().optional(),
  quote_count: z.number(),
  converted_booking: contactConvertedBookingSchema.nullable(),
});
export type ContactEnquiryHistoryItem = z.infer<typeof contactEnquiryHistorySchema>;

export const contactEnquiryHistoryResponseSchema = paginated(contactEnquiryHistorySchema);
