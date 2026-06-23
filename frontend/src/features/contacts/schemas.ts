import { z } from "zod";
import i18n from "@/i18n";
import { paginated } from "@/lib/api/pagination";
import { bookingStatusSchema } from "@/features/bookings/schemas";
import { enquiryStatusSchema } from "@/features/enquiries/schemas";
import { orgStatusSchema, orgTypeSchema } from "@/features/companies/schemas";

// The agent's agency (GAP-046): the contact API exposes a writable `agency` PK
// plus a read-only nested `agency_detail`. Reusing the companies enums keeps
// `agency_detail` structurally assignable to `Company`, so the form can seed the
// CompanyPicker straight from it without a cast.
export const agencyDetailSchema = z.object({
  id: z.number(),
  name: z.string(),
  org_type: orgTypeSchema,
  status: orgStatusSchema,
});
export type AgencyDetail = z.infer<typeof agencyDetailSchema>;

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
    // GAP-046: the free-text `company` was replaced by an `Organisation` FK; the
    // form sends the agency's PK (or null to clear it).
    agency: z.number().nullable().optional(),
    website_url: z.string().trim().max(255).optional(),
    preferred_method: z.string().trim().max(40).optional(),
    address_line_1: z.string().trim().max(255).optional(),
    address_line_2: z.string().trim().max(255).optional(),
    // GAP-042: town/post_code are editable; country edit is deferred (read-only).
    town: z.string().trim().max(128).optional(),
    post_code: z.string().trim().max(32).optional(),
    notes: z.string().trim().max(2000).optional(),
    // GAP-040 F1: a fixed taxonomy (see PERSON_TAGS). PATCH replaces the whole
    // set; the backend canonicalises (sort + dedupe) and rejects unknown values.
    // Left optional (no `.default`) so a Partial<ContactWriteInput> PATCH can
    // omit it, and the create/write bodies don't force callers to send it.
    tags: z.array(z.string()).optional(),
  })
  .refine((v) => v.first_name || v.last_name || v.agency, {
    message: i18n.t("contacts:errors.name_or_agency_required"),
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
    agency: z.number().nullable().optional(),
    website_url: z.string().trim().max(255).optional(),
    preferred_method: z.string().trim().max(40).optional(),
    address_line_1: z.string().trim().max(255).optional(),
    address_line_2: z.string().trim().max(255).optional(),
    town: z.string().trim().max(128).optional(),
    post_code: z.string().trim().max(32).optional(),
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
  .refine((v) => v.first_name || v.last_name || v.agency, {
    message: i18n.t("contacts:errors.name_or_agency_required"),
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
  // GAP-046: `agency` is the writable FK PK; `agency_detail` is the read-only
  // resolved org (the common case is no agency → both null).
  agency: z.number().nullable().optional(),
  agency_detail: agencyDetailSchema.nullable().optional(),
  website_url: z.string().nullable().optional(),
  preferred_method: z.string().nullable().optional(),
  address_line_1: z.string().nullable().optional(),
  address_line_2: z.string().nullable().optional(),
  // GAP-042: town/post_code/country round-trip; country is read-only (display
  // name resolved server-side as country_name).
  town: z.string().nullable().optional(),
  post_code: z.string().nullable().optional(),
  country: z.number().nullable().optional(),
  country_name: z.string().nullable().optional(),
  notes: z.string().nullable().optional(),
  status: z.string().nullable().optional(),
  // GAP-042: derived booking summary for the "Repeat" badge (property-agnostic,
  // >= 1 booking). Left `.optional()` (no `.default`, like `tags`) so the
  // inferred `Contact` stays assignable from existing fixtures; consumers read
  // `?? 0` / `?? false`.
  booking_count: z.number().optional(),
  is_repeat_customer: z.boolean().optional(),
  emails: z.array(contactEmailSchema).optional().default([]),
  phones: z.array(contactPhoneSchema).optional().default([]),
  // GAP-040 F1: a fixed taxonomy of customer tags (see PERSON_TAGS). Left
  // `.optional()` (no `.default`) so the inferred `Contact.tags` stays
  // `string[] | undefined` and existing fixtures/call sites needn't be updated;
  // every consumer reads it as `contact.tags ?? []`.
  tags: z.array(z.string()).optional(),
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
  agency: z.number().nullable().optional(),
  agency_detail: agencyDetailSchema.nullable().optional(),
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
  tags: z.array(z.string()).optional(),
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

// `/contacts/{id}/enquiries` enquiry-history shape (GAP-045 D2). Contacts owns
// its own copy of the schema; it superseded the old `/guests/{id}/enquiries`
// surface, which was retired in D4.
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

// GAP-042: `/contacts/{id}/bookings` previous-booking history (mirrors the
// backend ContactBookingSerializer). `property` is the bare FK pk — the shallow
// read doesn't resolve a name, so the row shows reference + status + dates.
export const contactBookingHistorySchema = z.object({
  id: z.number(),
  reference: z.string(),
  status: bookingStatusSchema,
  property: z.number().nullable().optional(),
  date_from: z.string().nullable().optional(),
  date_to: z.string().nullable().optional(),
  adults: z.number().nullable().optional(),
  children: z.number().nullable().optional(),
  is_archived: z.boolean().optional(),
  created_at: z.string().nullable().optional(),
});
export type ContactBookingHistoryItem = z.infer<typeof contactBookingHistorySchema>;

export const contactBookingHistoryResponseSchema = paginated(contactBookingHistorySchema);

// GAP-041 F2: `/contacts/{id}/relationships`. A row is a single directed link
// (from_person → to_person) seen from this contact's side: `direction` is
// "outgoing" when this contact is the from_person, "incoming" when it's the
// to_person. `kind` is the raw stored kind; `kind_label` is the backend's
// ENGLISH label and is tolerated but NEVER rendered — the UI computes its own
// localized label from `kind` + `direction` (see relationshipLabelKey).
export const relationshipPersonSchema = z.object({
  id: z.number(),
  first_name: z.string().nullable().optional(),
  last_name: z.string().nullable().optional(),
  display_name: z.string().nullable().optional(),
  kind: z.string(),
});
export type RelationshipPerson = z.infer<typeof relationshipPersonSchema>;

export const linkedContactSchema = z.object({
  id: z.number(),
  kind: z.string(),
  kind_label: z.string(),
  note: z.string(),
  other_person: relationshipPersonSchema,
  direction: z.enum(["outgoing", "incoming"]),
  created_at: z.string(),
});
export type LinkedContact = z.infer<typeof linkedContactSchema>;

export const linkedContactsResponseSchema = paginated(linkedContactSchema);

export const relationshipWriteInputSchema = z.object({
  // `.positive()` so the empty default (0, no contact picked) fails client-side
  // with a "choose a contact" message instead of POSTing to_person:0 and bouncing
  // off the backend's PK validation.
  to_person: z.number().int().positive(i18n.t("contacts:errors.linked_contact_required")),
  kind: z.string().min(1, i18n.t("contacts:errors.relationship_kind_required")),
  note: z.string().trim().max(2000).optional(),
});
export type RelationshipWriteInput = z.infer<typeof relationshipWriteInputSchema>;
