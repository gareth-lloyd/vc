import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { server } from "@/test/msw/server";
import { drfPage } from "@/test/drf";
import { searchQuoteOptions } from "../api";
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
};

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
      http.post("/api/v1/pricing:quote-bulk", async ({ request }) => {
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
      http.post("/api/v1/pricing:quote-bulk", () =>
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
      http.post("/api/v1/pricing:quote-bulk", () =>
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

  it("carries the plan/card enrichment fields through to the option", async () => {
    server.use(
      http.get("/api/v1/properties", () =>
        HttpResponse.json(
          drfPage([
            { id: 19, name: "Villa Sol", display_name: "Villa Sol", slug: null, status: "active" },
          ]),
        ),
      ),
      http.post("/api/v1/pricing:quote-bulk", () =>
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
      http.post("/api/v1/pricing:quote-bulk", () =>
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
      http.post("/api/v1/pricing:quote-bulk", () =>
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
      http.post("/api/v1/pricing:quote-bulk", () =>
        HttpResponse.json({
          quotes: [{ property_id: 9, available: false, error_code: "no_rate_available" }],
        }),
      ),
    );

    const result = await searchQuoteOptions(criteria);

    expect(result.options[0].currency).toBeNull();
  });

  it("returns an empty page without pricing when no candidates match", async () => {
    let priced = false;
    server.use(
      http.get("/api/v1/properties", () => HttpResponse.json(drfPage([]))),
      http.post("/api/v1/pricing:quote-bulk", () => {
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
