import type { EnquiryDetail } from "@/features/enquiries/schemas";
import { addDaysIso } from "@/lib/format/date";
import { nightsCount } from "@/lib/nights";
import type { QuoteCriteriaInput, QuoteSearchForm } from "./schemas";

/**
 * Pure translation between the operator's arrival-window search form (GAP-043)
 * and the unchanged `search-options` wire criteria.
 *
 * The backend searches arrivals in `preferred ± flex_days` — a symmetric
 * window. To land that on the asymmetric `[arrive_from, arrive_to]` the form
 * expresses, we put the preferred arrival at the window's midpoint (rounded
 * up): `flex = ceil(W / 2)`, `preferred = arrive_from + flex`. The resulting
 * span is `[arrive_from, arrive_from + 2 * ceil(W / 2)]` — exactly the window
 * for even widths, one day long on the late side for odd widths, and never
 * earlier than `arrive_from`, so no client-side filtering is needed.
 */
export function searchFormToCriteria(form: QuoteSearchForm): QuoteCriteriaInput {
  const width = form.specific_date ? 0 : nightsCount(form.arrive_from, form.arrive_to);
  const flex = Math.ceil(width / 2);
  const preferredFrom = addDaysIso(form.arrive_from, flex);
  return {
    date_from: preferredFrom,
    date_to: addDaysIso(preferredFrom, form.weeks * 7),
    adults: form.adults,
    children: form.children,
    country: form.country,
    region: form.region,
    min_bedrooms: form.min_bedrooms,
    max_bedrooms: form.max_bedrooms,
    q: form.q,
    flex_days: flex,
  };
}

type EnquirySeed = Pick<
  EnquiryDetail,
  "date_from" | "date_to" | "flexibility_days" | "adults" | "children" | "min_bedrooms"
>;

/**
 * Seed the search form from an enquiry. The enquiry's `flexibility_days` is a
 * symmetric ± spread around its dates, so the window seeds as
 * `date_from ± flexibility_days` — which `searchFormToCriteria` maps straight
 * back to `preferred = date_from, flex = flexibility_days`, reproducing
 * exactly the arrival window the enquiry expressed. `flexibility_days` is
 * still capped at 3 on intake (widening deferred to GAP-039), so the seeded
 * window is tight and collapses to a specific-date search when there is no
 * spread at all.
 */
export function enquiryToSearchForm(enquiry: EnquirySeed): Partial<QuoteSearchForm> {
  const dateFrom = enquiry.date_from ?? "";
  const flexDays = enquiry.flexibility_days ?? 0;
  const nights =
    enquiry.date_from && enquiry.date_to ? nightsCount(enquiry.date_from, enquiry.date_to) : 0;
  return {
    arrive_from: dateFrom ? addDaysIso(dateFrom, -flexDays) : "",
    arrive_to: dateFrom ? addDaysIso(dateFrom, flexDays) : "",
    weeks: Math.round(nights / 7) || 1,
    specific_date: flexDays === 0,
    adults: enquiry.adults,
    children: enquiry.children ?? 0,
    min_bedrooms: enquiry.min_bedrooms ?? null,
  };
}
