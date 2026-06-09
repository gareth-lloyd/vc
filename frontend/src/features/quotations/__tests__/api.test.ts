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
      http.post("/api/v1/pricing:quote-bulk", () =>
        HttpResponse.json({
          quotes: [{ property_id: 7, available: true, total: "4500.00", currency_code: "USD" }],
        }),
      ),
    );

    const result = await searchQuoteOptions(criteria, "USD");

    expect(seenPage).toBeNull(); // page 1 is left off the query
    expect(result.options).toHaveLength(1);
    expect(result.hasMore).toBe(true);
    expect(result.totalMatched).toBe(2);
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

    const result = await searchQuoteOptions(criteria, "USD", 2);

    expect(seenPage).toBe("2");
    expect(result.hasMore).toBe(false);
    expect(result.totalMatched).toBe(2);
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

    const result = await searchQuoteOptions(criteria, "USD");

    expect(result.options).toEqual([]);
    expect(result.hasMore).toBe(false);
    expect(priced).toBe(false);
  });
});
