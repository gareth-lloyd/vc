import { z } from "zod";
import { paginated } from "@/lib/api/pagination";

// --- reads ----------------------------------------------------------------

// The catalogue row — identity + provenance only, no bodies. `title` is the
// human-facing label; `updated_by_id` matches the serializer (an integer FK id,
// null before the first publish).
export const emailTemplateListItemSchema = z.object({
  key: z.string(),
  title: z.string(),
  version: z.number(),
  is_active: z.boolean(),
  updated_at: z.string(),
  updated_by_id: z.number().nullable(),
});
export type EmailTemplateListItem = z.infer<typeof emailTemplateListItemSchema>;

export const emailTemplatesListResponseSchema = paginated(emailTemplateListItemSchema);

// A single version with its authored + compiled bodies. `body_template_html` is
// the server-compiled output of the MJML — read-only, never editable. There's no
// plaintext field: it's derived from the rendered HTML at send time.
export const emailTemplateDetailSchema = emailTemplateListItemSchema.extend({
  subject_template: z.string(),
  body_template_mjml: z.string(),
  body_template_html: z.string(),
  notes: z.string(),
});
export type EmailTemplateDetail = z.infer<typeof emailTemplateDetailSchema>;

// `versions` returns a bare array (not paginated), newest first.
export const emailTemplateVersionsResponseSchema = z.array(emailTemplateDetailSchema);

// --- preview --------------------------------------------------------------

export const templatePreviewResponseSchema = z.object({
  rendered_subject: z.string(),
  rendered_body_html: z.string(),
  rendered_body_text: z.string(),
});
export type TemplatePreviewResponse = z.infer<typeof templatePreviewResponseSchema>;

// --- test-send ------------------------------------------------------------

// We only need the new log's id + status to confirm the send in a toast.
export const testSendResponseSchema = z.object({
  id: z.number(),
  status: z.string(),
});
export type TestSendResponse = z.infer<typeof testSendResponseSchema>;

// --- write inputs ---------------------------------------------------------

// Powers `zodResolver` on the Edit tab. The MJML is the only authored body
// source (plaintext is derived from it at send time), so it's required.
export const emailTemplatePublishInputSchema = z.object({
  title: z.string().trim().min(1, { message: "common:zod.invalid_type" }),
  subject_template: z.string().trim().min(1, { message: "common:zod.invalid_type" }),
  body_template_mjml: z.string().trim().min(1, { message: "common:zod.invalid_type" }),
  notes: z.string().optional(),
});
export type EmailTemplatePublishInput = z.infer<typeof emailTemplatePublishInputSchema>;

// Create adds the free-text `key`. A typo here creates an orphan key that
// nothing ever sends, so it's validated to a non-empty dotted-ish string.
export const emailTemplateCreateInputSchema = emailTemplatePublishInputSchema.extend({
  key: z
    .string()
    .trim()
    .min(1, { message: "common:zod.invalid_type" })
    .regex(/^[\w.]+$/, { message: "admin:email_templates.errors.invalid_key" }),
});
export type EmailTemplateCreateInput = z.infer<typeof emailTemplateCreateInputSchema>;

// --- preview/test-send request bodies (not RHF-bound) ---------------------

// The context source the operator previews / test-sends against. `none` renders
// against an empty context (Django fills missing vars with ""); the id sources
// dispatch to the backend's domain context builders; `json` is a raw merge dict.
export type ContextSource =
  | { kind: "none" }
  | { kind: "booking"; bookingId: number }
  | { kind: "quotation"; quotationId: number }
  | { kind: "json"; context: Record<string, unknown> };

// Turn the operator's chosen context source into the request fields the
// preview/test-send endpoints understand. Shared by both so the mapping lives
// in one place.
export function contextToRequest(source: ContextSource): {
  booking_id?: number;
  quotation_id?: number;
  context?: Record<string, unknown>;
} {
  switch (source.kind) {
    case "booking":
      return { booking_id: source.bookingId };
    case "quotation":
      return { quotation_id: source.quotationId };
    case "json":
      return { context: source.context };
    case "none":
      return {};
  }
}

export interface TemplatePreviewRequest {
  subject_template?: string;
  body_template_mjml?: string;
  booking_id?: number;
  quotation_id?: number;
  context?: Record<string, unknown>;
}

export interface TestSendRequest {
  to?: string;
  booking_id?: number;
  quotation_id?: number;
  context?: Record<string, unknown>;
}

export interface EmailTemplateFilters {
  key?: string;
}
