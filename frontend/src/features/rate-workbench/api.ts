import { apiSend } from "@/lib/api/client";
import type { PropertyId } from "@/lib/query/keys";
import {
  discountSchema,
  extraSchema,
  type Discount,
  type Extra,
} from "@/features/properties/schemas";
import {
  priceQuoteSchema,
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

// Read-only live probe against the pricing engine (colon-verb custom action).
// Domain failures (e.g. no_rate_available) surface as a 409 ApiError.
export async function runPriceProbe(body: PriceProbeRequest): Promise<PriceQuote> {
  const data = await apiSend<unknown>("POST", "/pricing:quote", body);
  return priceQuoteSchema.parse(data);
}
