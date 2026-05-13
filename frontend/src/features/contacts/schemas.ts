import { z } from "zod";
import { paginated } from "@/lib/api/pagination";

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
  email: z.string().email("Enter a valid email").max(254),
  label: z.string().trim().max(40).optional(),
  is_primary: z.boolean().optional(),
});
export type ContactEmailWriteInput = z.infer<typeof contactEmailWriteInputSchema>;

export const contactPhoneWriteInputSchema = z.object({
  number: z.string().trim().min(1, "Required").max(40),
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
    message: "At least a name or company is required",
    path: ["first_name"],
  });
export type ContactWriteInput = z.infer<typeof contactWriteInputSchema>;

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

export const contactListItemSchema = z.object({
  id: z.number(),
  title: z.string().nullable().optional(),
  first_name: z.string().nullable().optional(),
  last_name: z.string().nullable().optional(),
  company: z.string().nullable().optional(),
  status: z.string().nullable().optional(),
  primary_email: z.string().nullable().optional(),
  primary_phone: z.string().nullable().optional(),
});
export type ContactListItem = z.infer<typeof contactListItemSchema>;

export const contactsListResponseSchema = paginated(contactListItemSchema);

export interface ContactFilters {
  q?: string;
  status?: string;
  ordering?: string;
  page?: number;
}

export const contactListFiltersSchema = z.object({
  q: z.string().optional(),
  status: z.string().optional(),
  ordering: z.string().optional(),
  page: z.number().optional(),
});
