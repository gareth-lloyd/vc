import { z } from "zod";
import i18n from "@/i18n";
import { paginated } from "@/lib/api/pagination";

// The serialized agency value is "agency"; the other org types ("mgmt",
// "supplier") are accepted on read so the detail/list schemas never reject a
// row, even though this UI only ever creates/filters agencies.
export const orgTypeSchema = z.enum(["agency", "mgmt", "supplier"]);
export type OrgType = z.infer<typeof orgTypeSchema>;

export const orgStatusSchema = z.enum(["active", "inactive"]);
export type OrgStatus = z.infer<typeof orgStatusSchema>;

// Field ceilings mirror the backend Organisation model max_lengths exactly, so a
// value that passes client validation can never 400 server-side (name 128,
// phone 32, address 255, town 128, post_code 32, email 254, website_url 200).
export const companyWriteInputSchema = z.object({
  name: z.string().trim().min(1, i18n.t("common:errors.field_required")).max(128),
  email: z
    .string()
    .trim()
    .max(254)
    .optional()
    .refine((v) => !v || z.string().email().safeParse(v).success, {
      message: i18n.t("common:zod.invalid_email"),
    }),
  phone: z.string().trim().max(32).optional(),
  address_line_1: z.string().trim().max(255).optional(),
  address_line_2: z.string().trim().max(255).optional(),
  town: z.string().trim().max(128).optional(),
  post_code: z.string().trim().max(32).optional(),
  website_url: z.string().trim().max(200).optional(),
  notes: z.string().trim().max(2000).optional(),
});
export type CompanyWriteInput = z.infer<typeof companyWriteInputSchema>;

// The create form reuses the write fields verbatim — `org_type` is injected by
// the API layer (always "agency" from this directory), never collected here.
export const companyCreateInputSchema = companyWriteInputSchema;
export type CompanyCreateInput = z.infer<typeof companyCreateInputSchema>;

export const companySchema = z.object({
  id: z.number(),
  name: z.string(),
  org_type: orgTypeSchema,
  status: orgStatusSchema,
  email: z.string().nullable().optional(),
  phone: z.string().nullable().optional(),
  address_line_1: z.string().nullable().optional(),
  address_line_2: z.string().nullable().optional(),
  town: z.string().nullable().optional(),
  post_code: z.string().nullable().optional(),
  website_url: z.string().nullable().optional(),
  notes: z.string().nullable().optional(),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
});
export type Company = z.infer<typeof companySchema>;

export const companyListItemSchema = z.object({
  id: z.number(),
  name: z.string(),
  org_type: orgTypeSchema,
  status: orgStatusSchema,
  email: z.string().nullable().optional(),
  phone: z.string().nullable().optional(),
  town: z.string().nullable().optional(),
});
export type CompanyListItem = z.infer<typeof companyListItemSchema>;

export const companiesListResponseSchema = paginated(companyListItemSchema);

export interface CompanyFilters {
  // The backend's SearchFilter reads `search` (DRF default), not `q` — the
  // contacts directory's `q` is a pre-existing divergence we don't copy here.
  search?: string;
  status?: string;
  ordering?: string;
  page?: number;
}
