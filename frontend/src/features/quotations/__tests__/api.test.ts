import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { server } from "@/test/msw/server";
import { drfPage } from "@/test/drf";
import {
  holdQuotationLine,
  releaseQuotationLineHold,
  repriceStayOption,
  searchQuoteOptions,
} from "../api";
import type { QuoteCriteriaInput } from "../schemas";

const criteria: QuoteCriteriaInput = {
  date_from: "2026-07-01",
  date_to: "2026-07-08",
  adults: 2,
  children: 0,
  country: "",
  region: "",
  min_bedrooms: null,
  max_bedrooms: null,
  q: "",
  flex_days: 0,
};

// A candidate row whose requested dates are flagged unavailable.
function heldCandidateRow(id: number) {
  return {
    id,
    name: "Villa Sol",
    display_name: "Villa Sol",
    slug: "villa-sol",
    status: "active",
    available_for_range: false,
  };
}

afterEach(() => server.resetHandlers());

describe("searchQuoteOptions", () => {
  it("omits page on the first request and reports more pages from DRF next", async () => {
    let seenPage: string | null = "unset";
    let bulkBody: Record<string, unknown> | null = null;
    server.use(
      http.get("/api/v1/properties", ({ request }) => {
        seenPage = new URL(request.url).searchParams.get("page");
        return HttpResponse.json(
          drfPage(
            [
              {
                id: 7,
                name: "Villa Sol",
                display_name: "Villa Sol",
                slug: "villa-sol",
                status: "active",
              },
            ],
            { next: "http://api/v1/properties?page=2", count: 2 },
          ),
        );
      }),
      http.post("/api/v1/quotations:search-options", async ({ request }) => {
        bulkBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          quotes: [{ property_id: 7, available: true, total: "4500.00", currency_code: "USD" }],
        });
      }),
    );

    const result = await searchQuoteOptions(criteria);

    expect(seenPage).toBeNull(); // page 1 is left off the query
    expect(result.options).toHaveLength(1);
    expect(result.hasMore).toBe(true);
    expect(result.totalMatched).toBe(2);
    // No currency input (GAP-014): each property is priced in its own rate
    // plan's currency and reports it back per result.
    expect(bulkBody).not.toHaveProperty("currency");
    expect(result.options[0].currency).toBe("USD");
  });

  it("sends page=2 on a later page and reports the last page", async () => {
    let seenPage: string | null = "unset";
    server.use(
      http.get("/api/v1/properties", ({ request }) => {
        seenPage = new URL(request.url).searchParams.get("page");
        return HttpResponse.json(
          drfPage(
            [
              {
                id: 8,
                name: "Villa Luna",
                display_name: "Villa Luna",
                slug: "villa-luna",
                status: "active",
              },
            ],
            { count: 2 },
          ),
        );
      }),
      http.post("/api/v1/quotations:search-options", () =>
        HttpResponse.json({
          quotes: [{ property_id: 8, available: true, total: "5000.00", currency_code: "USD" }],
        }),
      ),
    );

    const result = await searchQuoteOptions(criteria, 2);

    expect(seenPage).toBe("2");
    expect(result.hasMore).toBe(false);
    expect(result.totalMatched).toBe(2);
  });

  it("carries the internal name and capacity through to the option", async () => {
    // Distinct villas can share a display_name — the row's internal `name`
    // and capacity are the disambiguators the results list renders.
    server.use(
      http.get("/api/v1/properties", () =>
        HttpResponse.json(
          drfPage([
            {
              id: 19,
              name: "Mary Gardens",
              display_name: "Villa Selene",
              slug: "mary-gardens",
              status: "active",
              capacity: {
                guests: 8,
                additional_guests: 0,
                bedrooms: 4,
                ensuites: 2,
                bathrooms: 3,
              },
            },
          ]),
        ),
      ),
      http.post("/api/v1/quotations:search-options", () =>
        HttpResponse.json({
          quotes: [{ property_id: 19, available: true, total: "1710.00", currency_code: "GBP" }],
        }),
      ),
    );

    const result = await searchQuoteOptions(criteria);

    expect(result.options[0].property_name).toBe("Villa Selene");
    expect(result.options[0].internal_name).toBe("Mary Gardens");
    expect(result.options[0].bedrooms).toBe(4);
    expect(result.options[0].sleeps).toBe(8);
  });

  it("requests geo ordering and carries region/country names through to the option", async () => {
    // GAP-078: the picker groups candidates country → region, so the
    // candidate query must ask the backend to bunch them (trailing `id`
    // keeps name collisions page-stable) and the row's geo names must
    // survive the merge onto the option.
    let seenOrdering: string | null = null;
    server.use(
      http.get("/api/v1/properties", ({ request }) => {
        seenOrdering = new URL(request.url).searchParams.get("ordering");
        return HttpResponse.json(
          drfPage([
            {
              id: 23,
              name: "Villa Thalassa",
              display_name: "Villa Thalassa",
              slug: "villa-thalassa",
              status: "active",
              region: 11,
              region_name: "Crete",
              country_name: "Greece",
            },
          ]),
        );
      }),
      http.post("/api/v1/quotations:search-options", () =>
        HttpResponse.json({
          quotes: [{ property_id: 23, available: true, total: "3200.00", currency_code: "EUR" }],
        }),
      ),
    );

    const result = await searchQuoteOptions(criteria);

    expect(seenOrdering).toBe("region__country__name,region__name,name,id");
    expect(result.options[0].region_name).toBe("Crete");
    expect(result.options[0].country_name).toBe("Greece");
  });

  it("carries the plan/card enrichment fields through to the option", async () => {
    server.use(
      http.get("/api/v1/properties", () =>
        HttpResponse.json(
          drfPage([
            { id: 19, name: "Villa Sol", display_name: "Villa Sol", slug: null, status: "active" },
          ]),
        ),
      ),
      http.post("/api/v1/quotations:search-options", () =>
        HttpResponse.json({
          quotes: [
            {
              property_id: 19,
              available: true,
              total: "1710.00",
              currency_code: "GBP",
              inclusion: "Daily maid service",
              occupancy_pricing: true,
              changeover_day: "sat",
              min_nights: 7,
              max_nights: 14,
              is_projected: false,
            },
          ],
        }),
      ),
    );

    const result = await searchQuoteOptions(criteria);

    expect(result.options[0]).toMatchObject({
      inclusion: "Daily maid service",
      occupancy_pricing: true,
      changeover_day: "sat",
      min_nights: 7,
      max_nights: 14,
      is_projected: false,
    });
  });

  it("defaults the enrichment fields to null on an enrichment-less response", async () => {
    server.use(
      http.get("/api/v1/properties", () =>
        HttpResponse.json(
          drfPage([
            { id: 9, name: "Villa Mar", display_name: "Villa Mar", slug: null, status: "active" },
          ]),
        ),
      ),
      http.post("/api/v1/quotations:search-options", () =>
        HttpResponse.json({
          quotes: [{ property_id: 9, available: true, total: "900.00", currency_code: "EUR" }],
        }),
      ),
    );

    const result = await searchQuoteOptions(criteria);

    expect(result.options[0].inclusion).toBeNull();
    expect(result.options[0].occupancy_pricing).toBeNull();
    expect(result.options[0].changeover_day).toBeNull();
    expect(result.options[0].min_nights).toBeNull();
  });

  it("leaves the option disambiguators null when the row has no capacity", async () => {
    server.use(
      http.get("/api/v1/properties", () =>
        HttpResponse.json(
          drfPage([
            { id: 9, name: "Villa Mar", display_name: "Villa Mar", slug: null, status: "active" },
          ]),
        ),
      ),
      http.post("/api/v1/quotations:search-options", () =>
        HttpResponse.json({
          quotes: [{ property_id: 9, available: true, total: "900.00", currency_code: "EUR" }],
        }),
      ),
    );

    const result = await searchQuoteOptions(criteria);

    expect(result.options[0].internal_name).toBe("Villa Mar");
    expect(result.options[0].bedrooms).toBeNull();
    expect(result.options[0].sleeps).toBeNull();
  });

  it("leaves the option currency null when a result has no currency_code", async () => {
    server.use(
      http.get("/api/v1/properties", () =>
        HttpResponse.json(
          drfPage([
            {
              id: 9,
              name: "Villa Mar",
              display_name: "Villa Mar",
              slug: "villa-mar",
              status: "active",
            },
          ]),
        ),
      ),
      // An unpriceable result reports no currency_code.
      http.post("/api/v1/quotations:search-options", () =>
        HttpResponse.json({
          quotes: [{ property_id: 9, available: false, error_code: "no_rate_available" }],
        }),
      ),
    );

    const result = await searchQuoteOptions(criteria);

    expect(result.options[0].currency).toBeNull();
  });

  it("sends flex_days with the preferred (unwidened) dates", async () => {
    let body: Record<string, unknown> | null = null;
    let candidateQuery: URLSearchParams | null = null;
    server.use(
      http.get("/api/v1/properties", ({ request }) => {
        candidateQuery = new URL(request.url).searchParams;
        return HttpResponse.json(
          drfPage([
            { id: 7, name: "Villa Sol", display_name: "Villa Sol", slug: null, status: "active" },
          ]),
        );
      }),
      http.post("/api/v1/quotations:search-options", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          quotes: [{ property_id: 7, available: true, total: "1400.00", currency_code: "GBP" }],
        });
      }),
    );

    await searchQuoteOptions({ ...criteria, flex_days: 2 });

    expect(body).toMatchObject({
      flex_days: 2,
      requests: [
        expect.objectContaining({ date_from: "2026-07-01", date_to: "2026-07-08" }) as unknown,
      ],
    });
    // The candidate query keeps the requested dates too — the backend doesn't
    // filter when include_unavailable is set, it only flags, so alternate-block
    // villas still reach pricing and `available_for_range` keeps meaning
    // "available on the requested dates".
    expect(candidateQuery!.get("date_from")).toBe("2026-07-01");
    expect(candidateQuery!.get("include_unavailable")).toBe("true");
  });

  it("maps stay_options through to the option", async () => {
    server.use(
      http.get("/api/v1/properties", () =>
        HttpResponse.json(
          drfPage([
            { id: 7, name: "Villa Sol", display_name: "Villa Sol", slug: null, status: "active" },
          ]),
        ),
      ),
      http.post("/api/v1/quotations:search-options", () =>
        HttpResponse.json({
          quotes: [
            {
              property_id: 7,
              available: true,
              total: "1400.00",
              currency_code: "GBP",
              stay_options: [
                {
                  date_from: "2026-07-04",
                  date_to: "2026-07-11",
                  nights: 7,
                  is_default: true,
                  is_available: true,
                },
                {
                  date_from: "2026-07-11",
                  date_to: "2026-07-18",
                  nights: 7,
                  is_default: false,
                  is_available: false,
                },
              ],
            },
          ],
        }),
      ),
    );

    const result = await searchQuoteOptions(criteria);

    expect(result.options[0].stay_options).toHaveLength(2);
    expect(result.options[0].stay_options?.[0].is_default).toBe(true);
  });

  it("keeps a held villa available when an alternate block is free", async () => {
    // The requested dates are held (available_for_range=false), but the
    // flexibility window offers a free block — that's exactly the case the
    // picker exists for, so the row must NOT be trumped to dates_unavailable.
    server.use(
      http.get("/api/v1/properties", () => HttpResponse.json(drfPage([heldCandidateRow(7)]))),
      http.post("/api/v1/quotations:search-options", () =>
        HttpResponse.json({
          quotes: [
            {
              property_id: 7,
              available: true,
              total: "1400.00",
              currency_code: "GBP",
              stay_options: [
                {
                  date_from: "2026-07-04",
                  date_to: "2026-07-11",
                  nights: 7,
                  is_default: true,
                  is_available: false,
                },
                {
                  date_from: "2026-07-11",
                  date_to: "2026-07-18",
                  nights: 7,
                  is_default: false,
                  is_available: true,
                },
              ],
            },
          ],
        }),
      ),
    );

    const result = await searchQuoteOptions(criteria);

    expect(result.options[0].available).toBe(true);
    expect(result.options[0].error_code).toBeNull();
  });

  it("still trumps to dates_unavailable when no offered block is free", async () => {
    server.use(
      http.get("/api/v1/properties", () => HttpResponse.json(drfPage([heldCandidateRow(7)]))),
      http.post("/api/v1/quotations:search-options", () =>
        HttpResponse.json({
          quotes: [
            {
              property_id: 7,
              available: true,
              total: "1400.00",
              currency_code: "GBP",
              stay_options: [
                {
                  date_from: "2026-07-04",
                  date_to: "2026-07-11",
                  nights: 7,
                  is_default: true,
                  is_available: false,
                },
              ],
            },
          ],
        }),
      ),
    );

    const result = await searchQuoteOptions(criteria);

    expect(result.options[0].available).toBe(false);
    expect(result.options[0].error_code).toBe("dates_unavailable");
  });

  it("still trumps to dates_unavailable when the response has no stay_options", async () => {
    server.use(
      http.get("/api/v1/properties", () => HttpResponse.json(drfPage([heldCandidateRow(7)]))),
      http.post("/api/v1/quotations:search-options", () =>
        HttpResponse.json({
          quotes: [{ property_id: 7, available: true, total: "1400.00", currency_code: "GBP" }],
        }),
      ),
    );

    const result = await searchQuoteOptions(criteria);

    expect(result.options[0].available).toBe(false);
    expect(result.options[0].error_code).toBe("dates_unavailable");
  });

  it("returns an empty page without pricing when no candidates match", async () => {
    let priced = false;
    server.use(
      http.get("/api/v1/properties", () => HttpResponse.json(drfPage([]))),
      http.post("/api/v1/quotations:search-options", () => {
        priced = true;
        return HttpResponse.json({ quotes: [] });
      }),
    );

    const result = await searchQuoteOptions(criteria);

    expect(result.options).toEqual([]);
    expect(result.hasMore).toBe(false);
    expect(priced).toBe(false);
  });
});

describe("repriceStayOption", () => {
  it("sends one request with flex_days 0 and parses the pricing fields", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/quotations:search-options", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          quotes: [
            {
              property_id: 7,
              available: true,
              total: "1400.00",
              currency_code: "GBP",
              date_from: "2026-07-11",
              date_to: "2026-07-18",
              changeover_shifted_from: null,
              inclusion: "Daily maid service",
            },
          ],
        });
      }),
    );

    const result = await repriceStayOption({
      property_id: 7,
      date_from: "2026-07-11",
      date_to: "2026-07-18",
      adults: 2,
      children: 0,
    });

    expect(body).toEqual({
      flex_days: 0,
      requests: [
        {
          property_id: 7,
          date_from: "2026-07-11",
          date_to: "2026-07-18",
          adults: 2,
          children: 0,
        },
      ],
    });
    expect(result.available).toBe(true);
    expect(result.total).toBe("1400.00");
    expect(result.inclusion).toBe("Daily maid service");
  });

  it("surfaces an error entry's code instead of throwing", async () => {
    server.use(
      http.post("/api/v1/quotations:search-options", () =>
        HttpResponse.json({
          quotes: [
            {
              property_id: 7,
              available: false,
              error_code: "min_nights_not_met",
              error_detail: "RateCard 3 requires min_nights=14, got 7",
            },
          ],
        }),
      ),
    );

    const result = await repriceStayOption({
      property_id: 7,
      date_from: "2026-07-11",
      date_to: "2026-07-18",
      adults: 2,
      children: 0,
    });

    expect(result.available).toBe(false);
    expect(result.error_code).toBe("min_nights_not_met");
  });

  it("parses the reprised week's occupancy bands (GAP-044b two-axis picker)", async () => {
    server.use(
      http.post("/api/v1/quotations:search-options", () =>
        HttpResponse.json({
          quotes: [
            {
              property_id: 7,
              available: true,
              total: "3690.22",
              currency_code: "GBP",
              date_from: "2026-08-01",
              date_to: "2026-08-08",
              occupancy_bands: [
                {
                  min_party: 1,
                  max_party: 8,
                  adults: 8,
                  total: "3690.22",
                  currency_code: "GBP",
                  is_poa: false,
                },
                {
                  min_party: 9,
                  max_party: 10,
                  adults: 10,
                  total: null,
                  currency_code: null,
                  is_poa: true,
                },
              ],
            },
          ],
        }),
      ),
    );

    const result = await repriceStayOption({
      property_id: 7,
      date_from: "2026-08-01",
      date_to: "2026-08-08",
      adults: 8,
      children: 0,
    });

    expect(result.occupancy_bands).toHaveLength(2);
    expect(result.occupancy_bands?.[0]).toMatchObject({
      min_party: 1,
      max_party: 8,
      total: "3690.22",
    });
    expect(result.occupancy_bands?.[1]).toMatchObject({ is_poa: true, total: null });
  });
});

describe("line hold endpoints", () => {
  it("holdQuotationLine POSTs to :hold and returns the parsed line", async () => {
    let called = false;
    server.use(
      http.post("/api/v1/quotations/7/lines/33:hold", () => {
        called = true;
        return HttpResponse.json({
          id: 33,
          hold: {
            id: 5,
            date_from: "2026-06-10",
            date_to: "2026-06-17",
            expires_at: "2026-06-13T12:00:00Z",
          },
        });
      }),
    );

    const line = await holdQuotationLine(7, 33);

    expect(called).toBe(true);
    expect(line.hold?.id).toBe(5);
  });

  it("releaseQuotationLineHold POSTs to :release-hold and returns the parsed line", async () => {
    let called = false;
    server.use(
      http.post("/api/v1/quotations/7/lines/33:release-hold", () => {
        called = true;
        return HttpResponse.json({ id: 33, hold: null });
      }),
    );

    const line = await releaseQuotationLineHold(7, 33);

    expect(called).toBe(true);
    expect(line.hold).toBeNull();
  });
});
