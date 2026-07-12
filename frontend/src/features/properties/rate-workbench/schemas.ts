import { z } from "zod";

/**
 * Write-input schemas for the Rate & Service Workbench inspectors (Unit 5).
 *
 * The read schemas (`extraSchema`/`Extra`, `discountSchema`/`Discount`) live in
 * `@/features/properties/schemas` and are imported, never redefined. These are
 * the form-facing write shapes only.
 *
 * The shapes below mirror the backend contract exactly (see `pricing/models`
 * and the `Extra`/`Discount` serializers): `kind`/`calc`/`rule_kind` are
 * constrained enums, `amount` and `currency` are required, and only the
 * genuinely-nullable columns (an Extra's `applies_from`/`applies_to`) may be
 * cleared to `null`. Discount `valid_from`/`valid_to` are NOT NULL, so they are
 * required here rather than nulled on blank.
 */

// Enum values mirror `pricing/enums.py`. They are typed data values (not UI
// copy), so components build i18n label keys from them — see the `enums.*`
// block in `properties.json`.
export const EXTRA_KINDS = [
  "cleaning",
  "pet_fee",
  "heating",
  "linen",
  "extra_bed",
  "service_fee",
  "resort_fee",
  "other",
] as const;
export const EXTRA_CALCS = [
  "fixed_per_stay",
  "fixed_per_night",
  "fixed_per_person",
  "fixed_per_person_per_night",
  "percent_of_subtotal",
] as const;
export const DISCOUNT_KINDS = ["percent", "fixed"] as const;
export const RULE_KINDS = [
  "length_of_stay",
  "early_bird",
  "last_minute",
  "repeat_guest",
  "promo_code",
] as const;
/** Rule kinds gated by a booking lead-time threshold (`threshold_days`). The
 * engine skips the lead-time check entirely when `threshold_days` is null, so
 * these kinds REQUIRE a threshold — a null one would apply unconditionally. */
export const THRESHOLD_RULE_KINDS = [
  "early_bird",
  "last_minute",
] as const satisfies readonly (typeof RULE_KINDS)[number][];

export const extraWriteInputSchema = z
  .object({
    name: z
      .string()
      .trim()
      .min(1, { message: "properties:rate_workbench.inspector.errors.extra_name_required" })
      .max(128),
    description: z.string().trim().nullable().optional(),
    // `kind`/`calc` are required NOT NULL enum columns with no server default.
    // The Selects only offer valid values, so a min(1) "pick one" guard is all
    // the client needs; the backend enforces the enum.
    kind: z.string().min(1, {
      message: "properties:rate_workbench.inspector.errors.extra_kind_required",
    }),
    calc: z.string().min(1, {
      message: "properties:rate_workbench.inspector.errors.extra_calc_required",
    }),
    amount: z
      .string()
      .trim()
      .min(1, { message: "properties:rate_workbench.inspector.errors.amount_required" }),
    // Writable FK (a Currency PK); the serializer's `currency_code` is read-only.
    currency: z
      .number({ message: "properties:rate_workbench.inspector.errors.extra_currency_required" })
      .int()
      .min(1, { message: "properties:rate_workbench.inspector.errors.extra_currency_required" }),
    is_mandatory: z.boolean().optional(),
    commissionable: z.boolean().optional(),
    applies_from: z.string().nullable().optional(),
    applies_to: z.string().nullable().optional(),
    is_active: z.boolean().optional(),
  })
  .refine((v) => !v.applies_from || !v.applies_to || v.applies_to >= v.applies_from, {
    path: ["applies_to"],
    message: "properties:rate_workbench.inspector.errors.extra_to_before_from",
  });
export type ExtraWriteInput = z.infer<typeof extraWriteInputSchema>;

/** Wire shape: only the genuinely-nullable date columns collapse to `null`. */
export type ExtraWritePayload = Omit<ExtraWriteInput, "applies_from" | "applies_to"> & {
  applies_from: string | null;
  applies_to: string | null;
};

export const discountWriteInputSchema = z
  .object({
    name: z
      .string()
      .trim()
      .min(1, { message: "properties:rate_workbench.inspector.errors.discount_name_required" })
      .max(128),
    code: z.string().trim().nullable().optional(),
    // Two distinct required enums: `rule_kind` (when the discount applies) and
    // `kind` (how the amount is read). The engine filters candidates by
    // rule_kind, so a missing one both 400s on create and never applies.
    rule_kind: z.string().min(1, {
      message: "properties:rate_workbench.inspector.errors.discount_rule_kind_required",
    }),
    kind: z.string().min(1, {
      message: "properties:rate_workbench.inspector.errors.discount_kind_required",
    }),
    amount: z
      .string()
      .trim()
      .min(1, { message: "properties:rate_workbench.inspector.errors.amount_required" }),
    min_nights: z.number().int().min(0).nullable().optional(),
    threshold_days: z.number().int().min(0).nullable().optional(),
    // NOT NULL on the model — required, never nulled on blank.
    valid_from: z
      .string()
      .min(1, { message: "properties:rate_workbench.inspector.errors.discount_dates_required" }),
    valid_to: z
      .string()
      .min(1, { message: "properties:rate_workbench.inspector.errors.discount_dates_required" }),
    max_uses: z.number().int().min(0).nullable().optional(),
    is_active: z.boolean().optional(),
    // NOTE: `uses_count` is deliberately omitted — it is read-only on the API
    // (DiscountSerializer.read_only_fields) and must never be written.
  })
  .refine((v) => !v.valid_from || !v.valid_to || v.valid_to >= v.valid_from, {
    path: ["valid_to"],
    message: "properties:rate_workbench.inspector.errors.discount_to_before_from",
  })
  // Lead-time kinds without a threshold would apply to EVERY booking in the
  // validity window (the engine skips the check when threshold_days is null).
  .refine(
    (v) =>
      !(THRESHOLD_RULE_KINDS as readonly string[]).includes(v.rule_kind) ||
      v.threshold_days != null,
    {
      path: ["threshold_days"],
      message: "properties:rate_workbench.inspector.errors.discount_threshold_required",
    },
  );
export type DiscountWriteInput = z.infer<typeof discountWriteInputSchema>;

/** Wire shape: an empty `code` collapses to `null` (a "" collides on the UNIQUE index). */
export type DiscountWritePayload = Omit<DiscountWriteInput, "code"> & { code: string | null };

// ---------------------------------------------------------------------------
// Carry-forward (GAP-069) — POST /properties/{id}/rate-plans:carry-forward.
// Promotes a projected future year into real editable rate rows. The only user
// input is the uplift %; `currency` (a Currency CODE string, not the FK id) and
// `target_year` are contextual and passed as props, not form fields.
// ---------------------------------------------------------------------------

export const carryForwardInputSchema = z.object({
  // An uplift, never a reduction (reductions are Q-018's separate concern). The
  // number input yields a number via the field's `setValueAs` (blank → 0), so
  // the schema stays a plain `z.number()` like every other numeric form field.
  uplift_pct: z
    .number({ message: "properties:rate_workbench.carry_forward.errors.uplift_invalid" })
    .min(0, { message: "properties:rate_workbench.carry_forward.errors.uplift_negative" }),
});
export type CarryForwardInput = z.infer<typeof carryForwardInputSchema>;

/** Wire shape: the form's uplift plus the two contextual, non-form props.
 * `currency` is the Currency CODE (e.g. "GBP"), which the endpoint resolves via
 * `Currency.code`; sending the numeric FK id would 404. */
export type CarryForwardPayload = CarryForwardInput & {
  currency: string;
  target_year: number;
};

// ---------------------------------------------------------------------------
// Live price probe (Unit 6) — POST /pricing:quote. The engine's breakdown is a
// flat dict of decimal STRINGS; the schemas below parse the fields we render —
// including owner economics (net_to_owner / commission / tax), trustworthy
// since the engine became `price_basis`-aware (BUG-009) — and `.passthrough()`
// the rest.
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
    band_id: z.number().nullable().optional(),
    // Back-compat: pre-SMELL-019 snapshots wrote `rule_id` (now `band_id`).
    rule_id: z.number().nullable().optional(),
    period_id: z.number().nullable().optional(),
    nightly: z.string(),
    // Q-018: the base nightly when that night's band carried a reduction
    // (`nightly` is the effective price the guest pays), else null/absent.
    reduced_from: z.string().nullable().optional(),
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
    commissionable: z.boolean().optional(),
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
    // Q-018: pre-reduction totals, present (non-null) only when at least one
    // night was priced from a reduced band — drives the "reduced from" cue.
    rate_subtotal_before_reduction: z.string().nullable().optional(),
    total_before_reduction: z.string().nullable().optional(),
    extras: z.array(appliedExtraSchema).default([]),
    extras_total: z.string().optional(),
    discount: z.string().optional(),
    total: z.string().optional(),
    plan_id: z.number().nullable().optional(),
    winning_period_id: z.number().nullable().optional(),
    changeover_shifted_from: z.string().nullable().optional(),
    changeover_day: z.string().nullable().optional(),
    is_projected: z.boolean().optional(),
    inclusion: z.string().nullable().optional(),
    min_nights: z.number().nullable().optional(),
    max_nights: z.number().nullable().optional(),
    occupancy_pricing: z.boolean().optional(),
    // Owner economics — basis-aware since BUG-009 landed. Optional/nullable so
    // older persisted shapes without them still parse (renderers hide the
    // owner section when absent).
    net_to_owner: z.string().nullable().optional(),
    commission: z.string().nullable().optional(),
    tax: z.string().nullable().optional(),
    price_basis: z.string().nullable().optional(),
  })
  .passthrough();
export type PriceQuote = z.infer<typeof priceQuoteSchema>;
