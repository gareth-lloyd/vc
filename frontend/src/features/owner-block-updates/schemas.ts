import { z } from "zod";
import { paginated } from "@/lib/api/pagination";

export const ownerBlockUpdateKindSchema = z.enum(["created", "cancelled"]);
export type OwnerBlockUpdateKind = z.infer<typeof ownerBlockUpdateKindSchema>;

export const ownerBlockKindSchema = z.enum(["owner_stay", "maintenance", "other"]);
export type OwnerBlockKind = z.infer<typeof ownerBlockKindSchema>;

export const ownerBlockStatusSchema = z.enum(["approved", "cancelled"]);
export type OwnerBlockStatus = z.infer<typeof ownerBlockStatusSchema>;

export const ownerBlockSummarySchema = z.object({
  id: z.number(),
  property: z.number().nullable(),
  property_name: z.string().nullable(),
  date_from: z.string(),
  date_to: z.string(),
  kind: ownerBlockKindSchema,
  notes: z.string(),
  status: ownerBlockStatusSchema,
  created_by: z.number().nullable(),
});
export type OwnerBlockSummary = z.infer<typeof ownerBlockSummarySchema>;

export const ownerBlockContestSchema = z.object({
  at: z.string(),
  by: z.number().nullable(),
  reason: z.string(),
});
export type OwnerBlockContest = z.infer<typeof ownerBlockContestSchema>;

export const ownerBlockUpdateSchema = z.object({
  id: z.number(),
  kind: ownerBlockUpdateKindSchema,
  actor: z.number().nullable(),
  created_at: z.string(),
  block: ownerBlockSummarySchema,
  contested: ownerBlockContestSchema.nullable(),
  is_seen: z.boolean(),
});
export type OwnerBlockUpdate = z.infer<typeof ownerBlockUpdateSchema>;

export const ownerBlockUpdatesResponseSchema = paginated(ownerBlockUpdateSchema);

// Contest write input — a non-blank reason is required (matches the endpoint).
export const contestWriteInputSchema = z.object({
  reason: z.string().min(1, "updates.errors.reason_required"),
});
export type ContestWriteInput = z.infer<typeof contestWriteInputSchema>;

export interface OwnerBlockUpdateFilters {
  seen?: boolean;
  property?: number;
}
