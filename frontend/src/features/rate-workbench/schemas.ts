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

// ---------------------------------------------------------------------------
// Live price probe (Unit 6) — POST /pricing:quote. The engine's breakdown is a
// flat dict of decimal STRINGS; the schemas below parse only the guest-facing
// fields we render and `.passthrough()` the rest (owner economics — net_to_owner
// / commission / tax — ride along on the wire but are deliberately never shown,
// per BUG-009's GROSS-plan mispricing).
// ---------------------------------------------------------------------------

export const priceProbeRequestSchema = z.object({
  property_id: z.number().int(),
  date_from: z
    .string()
    .min(1, { message: "properties:rate_workbench.probe.errors.dates_required" }),
  date_to: z.string().min(1, { message: "properties:rate_workbench.probe.errors.dates_required" }),
  adults: z.number().int().min(1),
  children: z.number().int().min(0).default(0),
  opt_in_extras: z.array(z.number().int()).default([]),
  discount_code: z.string().default(""),
});
export type PriceProbeRequest = z.infer<typeof priceProbeRequestSchema>;

export const quoteLineSchema = z
  .object({
    date: z.string(),
    rule_id: z.number().nullable().optional(),
    card_id: z.number().nullable().optional(),
    nightly: z.string(),
    notes: z.string().nullable().optional(),
  })
  .passthrough();

export const appliedExtraSchema = z
  .object({
    extra_id: z.number(),
    name: z.string(),
    kind: z.string().nullable().optional(),
    calc: z.string().nullable().optional(),
    computed_amount: z.string(),
  })
  .passthrough();

export const priceQuoteSchema = z
  .object({
    currency_code: z.string().nullable().optional(),
    party: z.number().nullable().optional(),
    date_from: z.string().optional(),
    date_to: z.string().optional(),
    lines: z.array(quoteLineSchema).default([]),
    rate_subtotal: z.string().optional(),
    extras: z.array(appliedExtraSchema).default([]),
    extras_total: z.string().optional(),
    discount: z.string().optional(),
    total: z.string().optional(),
    plan_id: z.number().nullable().optional(),
    winning_card_id: z.number().nullable().optional(),
    changeover_shifted_from: z.string().nullable().optional(),
    changeover_day: z.string().nullable().optional(),
    is_projected: z.boolean().optional(),
    inclusion: z.string().nullable().optional(),
    min_nights: z.number().nullable().optional(),
    max_nights: z.number().nullable().optional(),
    occupancy_pricing: z.boolean().optional(),
  })
  .passthrough();
export type PriceQuote = z.infer<typeof priceQuoteSchema>;
