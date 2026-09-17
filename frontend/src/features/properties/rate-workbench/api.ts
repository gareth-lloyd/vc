import { apiSend } from "@/lib/api/client";
import type { PropertyId } from "@/lib/query/keys";
import {
  discountSchema,
  extraSchema,
  ratePlanDetailSchema,
  type Discount,
  type Extra,
  type RatePlanDetail,
} from "@/features/properties/schemas";
import {
  confirmRatesResponseSchema,
  priceQuoteSchema,
  type CarryForwardPayload,
  type ConfirmRatesResponse,
  type DiscountWritePayload,
  type ExtraWritePayload,
  type PriceProbeRequest,
  type PriceQuote,
} from "./schemas";

// Extras: list/create are property-scoped (`/properties/{id}/extras`); the
// detail routes are flat (`/extras/{id}`) — see `django_res/pricing/urls.py`.
export async function createExtra(propertyId: PropertyId, body: ExtraWritePayload): Promise<Extra> {
  const data = await apiSend<unknown>("POST", `/properties/${propertyId}/extras`, body);
  return extraSchema.parse(data);
}

export async function updateExtra(
  extraId: number,
  body: Partial<ExtraWritePayload>,
): Promise<Extra> {
  const data = await apiSend<unknown>("PATCH", `/extras/${extraId}`, body);
  return extraSchema.parse(data);
}

export async function deleteExtra(extraId: number): Promise<void> {
  await apiSend<void>("DELETE", `/extras/${extraId}`);
}

// Discounts: list/create are property-scoped (`/properties/{id}/discounts`);
// the detail routes are flat (`/discounts/{id}`, via the DRF router).
export async function createDiscount(
  propertyId: PropertyId,
  body: DiscountWritePayload,
): Promise<Discount> {
  const data = await apiSend<unknown>("POST", `/properties/${propertyId}/discounts`, body);
  return discountSchema.parse(data);
}

export async function updateDiscount(
  discountId: number,
  body: Partial<DiscountWritePayload>,
): Promise<Discount> {
  const data = await apiSend<unknown>("PATCH", `/discounts/${discountId}`, body);
  return discountSchema.parse(data);
}

export async function deleteDiscount(discountId: number): Promise<void> {
  await apiSend<void>("DELETE", `/discounts/${discountId}`);
}

// Carry-forward (GAP-069): promote a projected future year into real editable
// rows. GAP-110: returns the anchor plan for the currency (never a new plan)
// in the RatePlanDetail shape with the target year's periods appended —
// usually the selected plan, but the backend resolves by (property, currency)
// only, so it can be the other-basis plan in the same currency. A 409
// `no_rate_available` means there is no prior year to carry from.
export async function carryForwardRatePlan(
  propertyId: PropertyId,
  body: CarryForwardPayload,
): Promise<RatePlanDetail> {
  const data = await apiSend<unknown>(
    "POST",
    `/properties/${propertyId}/rate-plans:carry-forward`,
    body,
  );
  return ratePlanDetailSchema.parse(data);
}

// GAP-114: mark a plan's carried (indicative) rates as owner-confirmed. The
// backend only touches live (non-historical) periods; the optional date window
// the endpoint accepts is not used here — the workbench confirms the whole plan.
export async function confirmRatePlanRates(ratePlanId: number): Promise<ConfirmRatesResponse> {
  const data = await apiSend<unknown>("POST", `/rate-plans/${ratePlanId}:confirm-rates`, {});
  return confirmRatesResponseSchema.parse(data);
}

// Read-only live probe against the pricing engine (colon-verb custom action).
// Domain failures (e.g. no_rate_available) surface as a 409 ApiError.
export async function runPriceProbe(body: PriceProbeRequest): Promise<PriceQuote> {
  const data = await apiSend<unknown>("POST", "/pricing:quote", body);
  return priceQuoteSchema.parse(data);
}
