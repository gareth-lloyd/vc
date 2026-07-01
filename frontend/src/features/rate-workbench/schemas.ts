import { z } from "zod";

/**
 * Write-input schemas for the Rate & Service Workbench inspectors (Unit 5).
 *
 * The read schemas (`extraSchema`/`Extra`, `discountSchema`/`Discount`) live in
 * `@/features/properties/schemas` and are imported, never redefined. These are
 * the form-facing write shapes only.
 *
 * `amount` is a plain form string (empty until typed); date fields are
 * `nullable().optional()` so an emptied input can be PATCHed as an explicit
 * `null` (clearing a band) rather than omitted — the same trap documented on
 * `propertyServiceWriteInputSchema`. The wire payloads below turn an empty
 * `amount`/date into that `null`.
 */
export const extraWriteInputSchema = z
  .object({
    name: z
      .string()
      .trim()
      .min(1, { message: "properties:rate_workbench.inspector.errors.extra_name_required" })
      .max(128),
    description: z.string().trim().nullable().optional(),
    kind: z.string().trim().nullable().optional(),
    amount: z.string().trim().optional(),
    currency_code: z.string().nullable().optional(),
    is_mandatory: z.boolean().optional(),
    applies_from: z.string().nullable().optional(),
    applies_to: z.string().nullable().optional(),
    is_active: z.boolean().optional(),
  })
  .refine((v) => !v.applies_from || !v.applies_to || v.applies_to >= v.applies_from, {
    path: ["applies_to"],
    message: "properties:rate_workbench.inspector.errors.extra_to_before_from",
  });
export type ExtraWriteInput = z.infer<typeof extraWriteInputSchema>;

/** Wire shape: an empty `amount`/date is sent as an explicit `null`. */
export type ExtraWritePayload = Omit<ExtraWriteInput, "amount"> & { amount: string | null };

export const discountWriteInputSchema = z
  .object({
    name: z
      .string()
      .trim()
      .min(1, { message: "properties:rate_workbench.inspector.errors.discount_name_required" })
      .max(128),
    code: z.string().trim().nullable().optional(),
    kind: z.string().trim().nullable().optional(),
    amount: z.string().trim().optional(),
    min_nights: z.number().int().min(0).nullable().optional(),
    threshold_days: z.number().int().min(0).nullable().optional(),
    valid_from: z.string().nullable().optional(),
    valid_to: z.string().nullable().optional(),
    max_uses: z.number().int().min(0).nullable().optional(),
    is_active: z.boolean().optional(),
    // NOTE: `uses_count` is deliberately omitted — it is read-only on the API
    // (DiscountSerializer.read_only_fields) and must never be written.
  })
  .refine((v) => !v.valid_from || !v.valid_to || v.valid_to >= v.valid_from, {
    path: ["valid_to"],
    message: "properties:rate_workbench.inspector.errors.discount_to_before_from",
  });
export type DiscountWriteInput = z.infer<typeof discountWriteInputSchema>;

/** Wire shape: an empty `amount`/date is sent as an explicit `null`. */
export type DiscountWritePayload = Omit<DiscountWriteInput, "amount"> & { amount: string | null };
