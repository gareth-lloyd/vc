import { z } from "zod";
import {
  PROPERTY_AVAILABILITY_DEFAULTS,
  PROPERTY_CHANGEOVER_DAYS,
  PROPERTY_PRICE_BASES,
} from "@/features/properties/schemas";

// percent/fixed calc types shared by commission, deposit, interim and
// security-deposit amounts (mirrors the backend *CalcType enums).
export const PROPERTY_DEFAULTS_CALC_TYPES = ["percent", "fixed"] as const;

export const SECURITY_DEPOSIT_PAYMENT_METHODS = [
  "card_hold",
  "card_charge",
  "bank_transfer",
] as const;

// GET/PATCH /property-defaults — the global creation-defaults singleton
// (GAP-070). Unlike PropertySettings/PropertyFinance these columns are
// NON-NULLABLE with server defaults, except `currency` (nullable FK) and the
// two check-in/out times.
export const propertyDefaultsSchema = z.object({
  availability_default: z.enum(PROPERTY_AVAILABILITY_DEFAULTS),
  bookings_require_pre_approval: z.boolean(),
  requires_enquiry_first: z.boolean(),
  currency: z.number().nullable(),
  check_in_time: z.string().nullable(),
  check_out_time: z.string().nullable(),
  changeover_day: z.enum(PROPERTY_CHANGEOVER_DAYS),
  min_nights_rental: z.number().int(),
  min_nights_rental_note: z.string(),
  prices_entered_as: z.enum(PROPERTY_PRICE_BASES),
  hold_duration_hours: z.number().int(),
  commission_calculation_type: z.enum(PROPERTY_DEFAULTS_CALC_TYPES),
  commission_amount: z.string(),
  commission_note: z.string(),
  tax_is_exempt: z.boolean(),
  tax_percentage: z.string(),
  deposit_required: z.boolean(),
  deposit_calculation_type: z.enum(PROPERTY_DEFAULTS_CALC_TYPES),
  deposit_amount: z.string(),
  interim_required: z.boolean(),
  interim_calculation_type: z.enum(PROPERTY_DEFAULTS_CALC_TYPES),
  interim_amount: z.string(),
  days_interim_due_before_arrival: z.number().int(),
  days_balance_due_before_arrival: z.number().int(),
  security_deposit_required: z.boolean(),
  security_deposit_calculation_type: z.enum(PROPERTY_DEFAULTS_CALC_TYPES),
  security_deposit_amount: z.string(),
  security_deposit_days_due_before_arrival: z.number().int(),
  security_deposit_days_refunded_after_departure: z.number().int(),
  security_deposit_payment_method: z.enum(SECURITY_DEPOSIT_PAYMENT_METHODS),
  cancellation_fee_amount: z.string(),
  cancellation_fee_percent: z.string(),
  cancellation_window_days: z.number().int(),
  cancellation_notes: z.string(),
  updated_at: z.string(),
});
export type PropertyDefaults = z.infer<typeof propertyDefaultsSchema>;

// Full-payload PATCH body — derived from the GET schema (drop `updated_at`,
// loosen the seven integer fields to accept a cleared → null value) so read
// and write stay in lockstep as columns change. Server-side non-null
// constraints are left to DRF: a cleared number input submits null and the
// resulting 400 surfaces as an inline field error via applyApiErrorToForm.
// Note/textarea fields deliberately stay plain strings so an emptied note
// submits "" — never null (the columns are non-nullable TextFields).
export const propertyDefaultsWriteInputSchema = propertyDefaultsSchema
  .omit({ updated_at: true })
  .extend({
    min_nights_rental: z.number().int().min(0).nullable(),
    hold_duration_hours: z.number().int().min(0).nullable(),
    days_interim_due_before_arrival: z.number().int().min(0).nullable(),
    days_balance_due_before_arrival: z.number().int().min(0).nullable(),
    security_deposit_days_due_before_arrival: z.number().int().min(0).nullable(),
    security_deposit_days_refunded_after_departure: z.number().int().min(0).nullable(),
    cancellation_window_days: z.number().int().min(0).nullable(),
  });
export type PropertyDefaultsWriteInput = z.infer<typeof propertyDefaultsWriteInputSchema>;
