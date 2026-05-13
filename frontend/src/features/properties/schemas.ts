import { z } from "zod";
import { paginated } from "@/lib/api/pagination";

export const propertyListItemSchema = z.object({
  id: z.number(),
  name: z.string(),
  display_name: z.string().nullable().optional(),
  slug: z.string().nullable().optional(),
  licence_number: z.string().nullable().optional(),
  status: z.string(),
  channel: z.string().nullable().optional(),
  category: z.number().nullable().optional(),
  group: z.number().nullable().optional(),
  region: z.number().nullable().optional(),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
});
export type PropertyListItem = z.infer<typeof propertyListItemSchema>;

export const propertyDetailSchema = propertyListItemSchema.extend({
  feature_ids: z.array(z.number()).optional().default([]),
  legacy_id: z.union([z.string(), z.number()]).nullable().optional(),
});
export type PropertyDetail = z.infer<typeof propertyDetailSchema>;

export const propertyListResponseSchema = paginated(propertyListItemSchema);

export const propertyDescriptionSchema = z.object({
  id: z.number(),
  title: z.string().nullable().optional(),
  body_html: z.string().nullable().optional(),
  body: z.string().nullable().optional(),
  language: z.string().nullable().optional(),
});
export type PropertyDescription = z.infer<typeof propertyDescriptionSchema>;

export const propertyDescriptionsResponseSchema = paginated(propertyDescriptionSchema);

export const propertyFeatureSchema = z.object({
  id: z.number(),
  name: z.string().optional(),
  slug: z.string().optional(),
});
export type PropertyFeature = z.infer<typeof propertyFeatureSchema>;

export const propertyFeaturesResponseSchema = paginated(propertyFeatureSchema);

export const propertyRoomSchema = z.object({
  id: z.number(),
  name: z.string().optional(),
  kind: z.string().nullable().optional(),
  count: z.number().nullable().optional(),
});
export type PropertyRoom = z.infer<typeof propertyRoomSchema>;

export const propertyRoomsResponseSchema = paginated(propertyRoomSchema);

export interface PropertyFilters {
  q?: string;
  country?: string;
  status?: string;
  ordering?: string;
  page?: number;
}
