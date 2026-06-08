import { apiGet, apiSend } from "@/lib/api/client";
import type { QueryParams } from "@/lib/api/url";
import type { Paginated } from "@/types/api";
import {
  emailTemplateDetailSchema,
  emailTemplatesListResponseSchema,
  emailTemplateVersionsResponseSchema,
  templatePreviewResponseSchema,
  testSendResponseSchema,
  type EmailTemplateDetail,
  type EmailTemplateFilters,
  type EmailTemplateListItem,
  type TemplatePreviewRequest,
  type TemplatePreviewResponse,
  type TestSendRequest,
  type TestSendResponse,
} from "./schemas";

// The backend keys templates by dotted `key` (`booking.confirmation`) and uses
// hyphenated path-segment actions (`/test-send`), NOT the FE's usual colon-verb
// convention — the API is shipped, so we call its exact paths. Keys never
// contain `/`, so `encodeURIComponent` is a safe round-trip.
function path(key: string, suffix = ""): string {
  return `/email-templates/${encodeURIComponent(key)}${suffix}`;
}

function toQuery(filters: EmailTemplateFilters): QueryParams {
  return { key: filters.key || undefined };
}

export async function fetchEmailTemplates(
  filters: EmailTemplateFilters,
): Promise<Paginated<EmailTemplateListItem>> {
  const data = await apiGet<unknown>("/email-templates", { query: toQuery(filters) });
  return emailTemplatesListResponseSchema.parse(data);
}

export async function fetchEmailTemplate(key: string): Promise<EmailTemplateDetail> {
  const data = await apiGet<unknown>(path(key));
  return emailTemplateDetailSchema.parse(data);
}

// PUT publishes a new active version (or v1 for a brand-new key) — used by both
// the Edit tab and the create page.
export async function publishEmailTemplate(
  key: string,
  body: {
    title: string;
    subject_template: string;
    body_template_mjml: string;
    notes?: string;
  },
): Promise<EmailTemplateDetail> {
  const data = await apiSend<unknown>("PUT", path(key), body);
  return emailTemplateDetailSchema.parse(data);
}

export async function previewEmailTemplate(
  key: string,
  body: TemplatePreviewRequest,
): Promise<TemplatePreviewResponse> {
  const data = await apiSend<unknown>("POST", path(key, "/preview"), body);
  return templatePreviewResponseSchema.parse(data);
}

export async function testSendEmailTemplate(
  key: string,
  body: TestSendRequest,
): Promise<TestSendResponse> {
  const data = await apiSend<unknown>("POST", path(key, "/test-send"), body);
  return testSendResponseSchema.parse(data);
}

export async function fetchEmailTemplateVersions(key: string): Promise<EmailTemplateDetail[]> {
  const data = await apiGet<unknown>(path(key, "/versions"));
  return emailTemplateVersionsResponseSchema.parse(data);
}
