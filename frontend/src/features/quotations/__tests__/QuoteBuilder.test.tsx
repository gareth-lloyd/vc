import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { geoLookupHandlers } from "@/test/msw/handlers";
import { drfPage } from "@/test/drf";
import { createTestQueryClient, renderWithProviders } from "@/test/render";
import { queryKeys } from "@/lib/query/keys";
import { useAuthStore } from "@/features/auth/store";
import type { EnquiryDetail } from "@/features/enquiries/schemas";
import { QuoteBuilder } from "../components/QuoteBuilder";

const enquiry: EnquiryDetail = {
  id: 99,
  reference: "ENQ-99",
  status: "new",
  person: 42,
  first_name: "Ada",
  last_name: "Lovelace",
  email: "ada@example.com",
  phone: "",
  contact_method: null,
  property: null,
  region: null,
  date_from: "2026-07-01",
  date_to: "2026-07-08",
  adults: 2,
  children: 0,
  request_type: "quote",
  assigned_to: null,
  agent: null,
  site_source: "main_website",
  created_at: "2026-05-01T10:00:00Z",
  updated_at: "2026-05-01T10:00:00Z",
  is_flexible: false,
  flexibility_days: 0,
  min_bedrooms: null,
  referral_code: "",
  inbound_message: "",
  lead_status: "warm",
  lost_reason: "",
  quotes_to_convert: null,
  quotations: [],
};

const villaProperty = {
  id: 7,
  name: "Villa Sol",
  display_name: "Villa Sol",
  slug: "villa-sol",
  status: "active",
};

const villaTwo = {
  id: 8,
  name: "Villa Luna",
  display_name: "Villa Luna",
  slug: "villa-luna",
  status: "active",
};

// Prices whatever property_ids the bulk request carries — lets a paged
// /properties mock drive which villas come back available.
function priceRequested() {
  return http.post("/api/v1/quotations:search-options", async ({ request }) => {
    const body = (await request.json()) as { requests: Array<{ property_id: number }> };
    return HttpResponse.json({
      quotes: body.requests.map((r) => ({
        property_id: r.property_id,
        available: true,
        total: "4500.00",
        currency_code: "USD",
      })),
    });
  });
}

function mockSaveFlow() {
  return [
    http.get("/api/v1/properties", () => HttpResponse.json(drfPage([villaProperty]))),
    http.post("/api/v1/quotations:search-options", () =>
      HttpResponse.json({
        quotes: [{ property_id: 7, available: true, total: "4500.00", currency_code: "USD" }],
      }),
    ),
    http.get("/api/v1/terms-versions/current", () =>
      HttpResponse.json({ id: 5, version: "v1", is_current: true, published_at: null }),
    ),
    http.post("/api/v1/quotations", () =>
      HttpResponse.json(
        { id: 50, reference: "QVC50", status: "draft", enquiry: 99 },
        { status: 201 },
      ),
    ),
  ];
}

function mockSearch() {
  return [
    http.get("/api/v1/properties", () => HttpResponse.json(drfPage([villaProperty]))),
    http.post("/api/v1/quotations:search-options", () =>
      HttpResponse.json({
        quotes: [{ property_id: 7, available: true, total: "4500.00", currency_code: "USD" }],
      }),
    ),
  ];
}

beforeEach(() => {
  useAuthStore.setState({ role: "RESERVATIONS", isSuperuser: false, status: "authenticated" });
  // The criteria form's country/region dropdowns fetch the geo lookups on
  // mount; none of these tests care about the option lists.
  server.use(...geoLookupHandlers);
});
afterEach(() => {
  useAuthStore.getState().clear();
  server.resetHandlers();
});

describe("QuoteBuilder", () => {
  it("invalidates the enquiry detail and completes when a draft is saved", async () => {
    server.use(...mockSaveFlow());
    const queryClient = createTestQueryClient();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const onComplete = vi.fn();

    renderWithProviders(<QuoteBuilder enquiry={enquiry} onComplete={onComplete} />, {
      queryClient,
    });

    await userEvent.click(await screen.findByRole("button", { name: /^search$/i }));
    await userEvent.click(await screen.findByRole("button", { name: /add to quote/i }));
    await userEvent.click(screen.getByRole("button", { name: /save draft/i }));
    await userEvent.click(await screen.findByRole("button", { name: /^save quote$/i }));

    // The new draft must refresh the enquiry's inline quote-stack in place.
    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: queryKeys.enquiries.detail(99) }),
    );
    // And the host is told which quotation was committed.
    expect(onComplete).toHaveBeenCalledWith(expect.objectContaining({ id: 50 }));
  });

  it("shows the enquiry summary header at the top of the builder", () => {
    renderWithProviders(<QuoteBuilder enquiry={enquiry} />);

    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("ENQ-99")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^edit$/i })).toBeInTheDocument();
  });

  it("prefills criteria from the enquiry", async () => {
    renderWithProviders(<QuoteBuilder enquiry={enquiry} />);

    // A no-flex enquiry seeds a specific-date search: the arrival window
    // collapses (Arrive-to hidden) and the 7-night stay rounds to 1 week.
    expect(await screen.findByLabelText(/arrive from/i)).toHaveValue("2026-07-01");
    expect(screen.queryByLabelText(/arrive to/i)).not.toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /search specific date/i })).toBeChecked();
    expect(screen.getByText(/1 week$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/adults/i)).toHaveValue(2);
  });

  it("searches without any currency selection and sends no currency to pricing", async () => {
    let bulkBody: Record<string, unknown> | null = null;
    server.use(
      http.get("/api/v1/properties", () => HttpResponse.json(drfPage([villaProperty]))),
      http.post("/api/v1/quotations:search-options", async ({ request }) => {
        bulkBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          quotes: [{ property_id: 7, available: true, total: "4500.00", currency_code: "USD" }],
        });
      }),
    );
    renderWithProviders(<QuoteBuilder enquiry={enquiry} />);

    // No forced currency selection anywhere in the criteria pane (GAP-014).
    expect(screen.queryByRole("combobox", { name: /currency/i })).not.toBeInTheDocument();

    await userEvent.click(await screen.findByRole("button", { name: /^search$/i }));
    expect(await screen.findByText("Villa Sol")).toBeInTheDocument();
    // Currency is an output of pricing, never an input to the search.
    await waitFor(() => expect(bulkBody).not.toBeNull());
    expect(bulkBody).not.toHaveProperty("currency");
  });

  it("renders mixed-currency results and shortlist lines each in their own currency", async () => {
    server.use(
      http.get("/api/v1/properties", () => HttpResponse.json(drfPage([villaProperty, villaTwo]))),
      http.post("/api/v1/quotations:search-options", () =>
        HttpResponse.json({
          quotes: [
            { property_id: 7, available: true, total: "4500.00", currency_code: "GBP" },
            { property_id: 8, available: true, total: "5200.00", currency_code: "EUR" },
          ],
        }),
      ),
    );
    renderWithProviders(<QuoteBuilder enquiry={enquiry} />);

    await userEvent.click(await screen.findByRole("button", { name: /^search$/i }));
    // One results list freely mixes currencies — each row prices in its own.
    expect(await screen.findByText("£4,500.00")).toBeInTheDocument();
    expect(screen.getByText("€5,200.00")).toBeInTheDocument();

    // Staged lines carry their own currency into the shortlist.
    const addButtons = screen.getAllByRole("button", { name: /add to quote/i });
    await userEvent.click(addButtons[0]);
    await userEvent.click(addButtons[1]);
    expect(await screen.findByText(/shortlist \(2\)/i)).toBeInTheDocument();
    expect(screen.getAllByText("£4,500.00")).toHaveLength(2); // result row + shortlist line
    expect(screen.getAllByText("€5,200.00")).toHaveLength(2);
  });

  it("adds a priced option into the shortlist", async () => {
    server.use(...mockSearch());
    renderWithProviders(<QuoteBuilder enquiry={enquiry} />);

    await userEvent.click(await screen.findByRole("button", { name: /^search$/i }));
    expect(await screen.findByText("Villa Sol")).toBeInTheDocument();

    // The shortlist starts empty, then carries the added villa.
    expect(screen.getByText(/your shortlist is empty/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /add to quote/i }));
    expect(await screen.findByText(/shortlist \(1\)/i)).toBeInTheDocument();
    expect(screen.getByText(/7 nights/i)).toBeInTheDocument();
  });

  it("seeds the staged line's inclusions from the winning plan", async () => {
    server.use(
      http.get("/api/v1/properties", () => HttpResponse.json(drfPage([villaProperty]))),
      http.post("/api/v1/quotations:search-options", () =>
        HttpResponse.json({
          quotes: [
            {
              property_id: 7,
              available: true,
              total: "4500.00",
              currency_code: "USD",
              inclusion: "Daily maid service",
            },
          ],
        }),
      ),
    );
    renderWithProviders(<QuoteBuilder enquiry={enquiry} />);

    await userEvent.click(await screen.findByRole("button", { name: /^search$/i }));
    // The result line surfaces the plan's inclusions…
    expect(await screen.findByText(/Daily maid service/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /add to quote/i }));
    // …and the staged shortlist line is pre-seeded with them (still editable).
    await userEvent.click(screen.getByRole("button", { name: /edit line/i }));
    expect(screen.getByLabelText(/inclusions/i)).toHaveValue("Daily maid service");
  });

  it("seeds the arrival window from the enquiry's ± flexibility and sends it on search", async () => {
    let searchBody: Record<string, unknown> | null = null;
    server.use(
      http.get("/api/v1/properties", () => HttpResponse.json(drfPage([villaProperty]))),
      http.post("/api/v1/quotations:search-options", async ({ request }) => {
        searchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          quotes: [{ property_id: 7, available: true, total: "4500.00", currency_code: "USD" }],
        });
      }),
    );
    renderWithProviders(<QuoteBuilder enquiry={{ ...enquiry, flexibility_days: 2 }} />);

    // The criteria form seeds a symmetric arrival window from the enquiry's
    // ± flexibility…
    expect(await screen.findByLabelText(/arrive from/i)).toHaveValue("2026-06-29");
    expect(screen.getByLabelText(/arrive to/i)).toHaveValue("2026-07-03");

    await userEvent.click(await screen.findByRole("button", { name: /^search$/i }));
    await screen.findByText("Villa Sol");

    // …which translates back to exactly the enquiry's preferred dates + flex.
    expect(searchBody).toMatchObject({
      flex_days: 2,
      requests: [
        expect.objectContaining({ date_from: "2026-07-01", date_to: "2026-07-08" }) as unknown,
      ],
    });
  });

  it("maps a wide arrival window to the backend's maximum ±21-day flex", async () => {
    let searchBody: Record<string, unknown> | null = null;
    server.use(
      http.get("/api/v1/properties", () => HttpResponse.json(drfPage([villaProperty]))),
      http.post("/api/v1/quotations:search-options", async ({ request }) => {
        searchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          quotes: [{ property_id: 7, available: true, total: "4500.00", currency_code: "USD" }],
        });
      }),
    );
    renderWithProviders(<QuoteBuilder enquiry={{ ...enquiry, flexibility_days: 3 }} />);

    // Widen the window to the 42-day maximum ("any week in June-ish sweep").
    const arriveTo = await screen.findByLabelText(/arrive to/i);
    await userEvent.clear(arriveTo);
    await userEvent.type(arriveTo, "2026-08-09"); // 42 days after 2026-06-28

    await userEvent.click(await screen.findByRole("button", { name: /^search$/i }));
    await screen.findByText("Villa Sol");
    expect(searchBody).toMatchObject({ flex_days: 21 });
  });

  it("stages and saves the picked block's dates and repriced total", async () => {
    // Wed 1 Jul → Wed 8 Jul ± 2 at a Sat-changeover villa: the backend offers
    // two Saturday blocks; the operator picks the later one, which reprices.
    // The save must persist the picked block's dates — even though both
    // blocks are the same length as the criteria stay.
    let saveBody: { lines: Array<Record<string, unknown>> } | null = null;
    server.use(
      http.get("/api/v1/properties", () => HttpResponse.json(drfPage([villaProperty]))),
      http.get("/api/v1/terms-versions/current", () =>
        HttpResponse.json({ id: 5, version: "v1", is_current: true, published_at: null }),
      ),
      http.post("/api/v1/quotations", async ({ request }) => {
        saveBody = (await request.json()) as { lines: Array<Record<string, unknown>> };
        return HttpResponse.json(
          { id: 50, reference: "QVC50", status: "draft", enquiry: 99 },
          { status: 201 },
        );
      }),
      http.post("/api/v1/quotations:search-options", async ({ request }) => {
        const body = (await request.json()) as { flex_days: number };
        if (body.flex_days === 0) {
          // The reprice for the picked block.
          return HttpResponse.json({
            quotes: [
              {
                property_id: 7,
                available: true,
                total: "5200.00",
                currency_code: "USD",
                date_from: "2026-07-11",
                date_to: "2026-07-18",
                inclusion: "Pool heating",
              },
            ],
          });
        }
        return HttpResponse.json({
          quotes: [
            {
              property_id: 7,
              available: true,
              total: "4500.00",
              currency_code: "USD",
              date_from: "2026-07-04",
              date_to: "2026-07-11",
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
                  is_available: true,
                },
              ],
            },
          ],
        });
      }),
    );
    renderWithProviders(<QuoteBuilder enquiry={{ ...enquiry, flexibility_days: 2 }} />);

    await userEvent.click(await screen.findByRole("button", { name: /^search$/i }));
    await screen.findByText("Villa Sol");

    // Keep only the later week checked (uncheck the pre-checked default).
    const cells = within(screen.getByRole("group", { name: /stay options/i })).getAllByRole(
      "checkbox",
    );
    await userEvent.click(cells[0]);
    await userEvent.click(cells[1]);
    await screen.findByText("$5,200.00");
    await userEvent.click(screen.getByRole("button", { name: /add to quote/i }));

    // The shortlist line carries the picked block, not the criteria dates.
    expect(await screen.findByText(/shortlist \(1\)/i)).toBeInTheDocument();
    expect(screen.getByText(/11 Jul 2026 – 18 Jul 2026/)).toBeInTheDocument();
    expect(screen.getAllByText("$5,200.00").length).toBeGreaterThan(0);

    // The saved line persists the picked block's dates, not just the display.
    await userEvent.click(screen.getByRole("button", { name: /save draft/i }));
    await userEvent.click(await screen.findByRole("button", { name: /^save quote$/i }));
    await waitFor(() => expect(saveBody).not.toBeNull());
    expect(saveBody!.lines[0]).toMatchObject({
      date_from: "2026-07-11",
      date_to: "2026-07-18",
    });
  });

  it("stages one line per checked week, dedups re-adds, and removes weeks independently (GAP-043)", async () => {
    let saveBody: { lines: Array<Record<string, unknown>> } | null = null;
    server.use(
      http.get("/api/v1/properties", () => HttpResponse.json(drfPage([villaProperty]))),
      http.get("/api/v1/terms-versions/current", () =>
        HttpResponse.json({ id: 5, version: "v1", is_current: true, published_at: null }),
      ),
      http.post("/api/v1/quotations", async ({ request }) => {
        saveBody = (await request.json()) as { lines: Array<Record<string, unknown>> };
        return HttpResponse.json(
          { id: 50, reference: "QVC50", status: "draft", enquiry: 99 },
          { status: 201 },
        );
      }),
      http.post("/api/v1/quotations:search-options", async ({ request }) => {
        const body = (await request.json()) as { flex_days: number };
        if (body.flex_days === 0) {
          // The alternate week's reprice.
          return HttpResponse.json({
            quotes: [
              {
                property_id: 7,
                available: true,
                total: "5200.00",
                currency_code: "USD",
                date_from: "2026-07-11",
                date_to: "2026-07-18",
              },
            ],
          });
        }
        return HttpResponse.json({
          quotes: [
            {
              property_id: 7,
              available: true,
              total: "4500.00",
              currency_code: "USD",
              date_from: "2026-07-04",
              date_to: "2026-07-11",
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
                  is_available: true,
                },
              ],
            },
          ],
        });
      }),
    );
    renderWithProviders(<QuoteBuilder enquiry={{ ...enquiry, flexibility_days: 2 }} />);

    await userEvent.click(await screen.findByRole("button", { name: /^search$/i }));
    await screen.findByText("Villa Sol");

    // Tick the alternate as well (the default is pre-checked) → 2 weeks stage
    // as two independent lines of the same villa.
    const cells = within(screen.getByRole("group", { name: /stay options/i })).getAllByRole(
      "checkbox",
    );
    await userEvent.click(cells[1]);
    await screen.findByText("$5,200.00");
    await userEvent.click(screen.getByRole("button", { name: /add 2 weeks/i }));
    expect(await screen.findByText(/shortlist \(2\)/i)).toBeInTheDocument();

    // Both weeks staged → the card flips to Added and can't re-add (dedup).
    expect(screen.getByRole("button", { name: /^added$/i })).toBeDisabled();

    // Removing one week keeps the other and frees that week for re-adding.
    await userEvent.click(screen.getAllByRole("button", { name: /^remove$/i })[0]);
    expect(await screen.findByText(/shortlist \(1\)/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /add to quote/i })).toBeEnabled();

    // Saving persists one line per staged week, each at its own dates.
    await userEvent.click(screen.getByRole("button", { name: /save draft/i }));
    await userEvent.click(await screen.findByRole("button", { name: /^save quote$/i }));
    await waitFor(() => expect(saveBody).not.toBeNull());
    expect(saveBody!.lines).toHaveLength(1);
    expect(saveBody!.lines[0]).toMatchObject({
      date_from: "2026-07-11",
      date_to: "2026-07-18",
    });
  });

  it("keeps the criteria dates when the default block is the same-length shifted stay", async () => {
    // The engine shifted Wed 1 Jul → Sat 4 Jul (GAP-007) but the stay length
    // is unchanged: the backend stays the single source of the shift, so the
    // saved line posts the criteria dates and lets the server re-shift.
    let saveBody: { lines: Array<Record<string, unknown>> } | null = null;
    server.use(
      http.get("/api/v1/properties", () => HttpResponse.json(drfPage([villaProperty]))),
      http.get("/api/v1/terms-versions/current", () =>
        HttpResponse.json({ id: 5, version: "v1", is_current: true, published_at: null }),
      ),
      http.post("/api/v1/quotations", async ({ request }) => {
        saveBody = (await request.json()) as { lines: Array<Record<string, unknown>> };
        return HttpResponse.json(
          { id: 50, reference: "QVC50", status: "draft", enquiry: 99 },
          { status: 201 },
        );
      }),
      http.post("/api/v1/quotations:search-options", () =>
        HttpResponse.json({
          quotes: [
            {
              property_id: 7,
              available: true,
              total: "4500.00",
              currency_code: "USD",
              date_from: "2026-07-04",
              date_to: "2026-07-11",
              stay_options: [
                {
                  date_from: "2026-07-04",
                  date_to: "2026-07-11",
                  nights: 7,
                  is_default: true,
                  is_available: true,
                },
              ],
            },
          ],
        }),
      ),
    );
    renderWithProviders(<QuoteBuilder enquiry={{ ...enquiry, flexibility_days: 2 }} />);

    await userEvent.click(await screen.findByRole("button", { name: /^search$/i }));
    await screen.findByText("Villa Sol");
    await userEvent.click(screen.getByRole("button", { name: /add to quote/i }));

    await userEvent.click(screen.getByRole("button", { name: /save draft/i }));
    await userEvent.click(await screen.findByRole("button", { name: /^save quote$/i }));
    await waitFor(() => expect(saveBody).not.toBeNull());
    expect(saveBody!.lines[0]).toMatchObject({
      date_from: "2026-07-01",
      date_to: "2026-07-08",
    });
  });

  it("loads and appends the next page of priced options on Load more", async () => {
    server.use(
      http.get("/api/v1/properties", ({ request }) => {
        const page = new URL(request.url).searchParams.get("page");
        // DRF reports the same total `count` on every page; page 1 advertises a
        // `next`, page 2 is the last page.
        if (page === "2") return HttpResponse.json(drfPage([villaTwo], { count: 2 }));
        return HttpResponse.json(
          drfPage([villaProperty], { next: "http://api/v1/properties?page=2", count: 2 }),
        );
      }),
      priceRequested(),
    );
    renderWithProviders(<QuoteBuilder enquiry={enquiry} />);

    await userEvent.click(await screen.findByRole("button", { name: /^search$/i }));
    expect(await screen.findByText("Villa Sol")).toBeInTheDocument();
    // One of two matching villas priced so far.
    expect(screen.getByText(/checked 1 of 2 matching villas/i)).toBeInTheDocument();

    // Page 1 advertised more → Load more appends page 2 without dropping page 1.
    await userEvent.click(screen.getByRole("button", { name: /load more/i }));
    expect(await screen.findByText("Villa Luna")).toBeInTheDocument();
    expect(screen.getByText("Villa Sol")).toBeInTheDocument();
    // Last page reached → the button is gone.
    expect(screen.queryByRole("button", { name: /load more/i })).not.toBeInTheDocument();
  });

  it("flags a date-held villa as unavailable instead of offering it", async () => {
    // The candidate search asks for the full set (include_unavailable) with the
    // stay window; a villa whose dates are already held/booked must land in the
    // unavailable bucket with no add affordance — even though the pricing
    // engine (which knows nothing about holds) priced it happily.
    // `null as …` keeps the declared union at the assertion sites — TS can't
    // see the closure assignment, and a bare `null` initializer narrows the
    // variable to `never` under `?.` access.
    let candidateParams = null as URLSearchParams | null;
    server.use(
      http.get("/api/v1/properties", ({ request }) => {
        const url = new URL(request.url);
        if (!url.searchParams.get("q")) candidateParams = url.searchParams;
        return HttpResponse.json(drfPage([{ ...villaProperty, available_for_range: false }]));
      }),
      priceRequested(),
    );
    renderWithProviders(<QuoteBuilder enquiry={enquiry} />);

    await userEvent.click(await screen.findByRole("button", { name: /^search$/i }));

    expect(await screen.findByText(/1 villa unavailable for these dates/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /add to quote/i })).not.toBeInTheDocument();
    // The stay window + include_unavailable rode on the candidate query.
    expect(candidateParams?.get("date_from")).toBe("2026-07-01");
    expect(candidateParams?.get("date_to")).toBe("2026-07-08");
    expect(candidateParams?.get("include_unavailable")).toBe("true");
  });

  it("does not advance the priced criteria when a re-search fails", async () => {
    // First search (Jul 1–8) succeeds; a re-search with an extended stay 500s.
    server.use(
      http.get("/api/v1/properties", () => HttpResponse.json(drfPage([villaProperty]))),
      http.post("/api/v1/quotations:search-options", async ({ request }) => {
        const body = (await request.json()) as { requests: Array<{ date_to: string }> };
        if (body.requests[0]?.date_to !== "2026-07-08") {
          return new HttpResponse(null, { status: 500 });
        }
        return HttpResponse.json({
          quotes: [{ property_id: 7, available: true, total: "4500.00", currency_code: "USD" }],
        });
      }),
    );
    renderWithProviders(<QuoteBuilder enquiry={enquiry} />);

    await userEvent.click(await screen.findByRole("button", { name: /^search$/i }));
    expect(await screen.findByText("Villa Sol")).toBeInTheDocument();

    // Extend the stay to 3 weeks (1 Jul + 21 nights = 22 Jul) and re-search →
    // the re-price 500s, leaving the original results on screen.
    const increase = screen.getByRole("button", { name: /increase number of weeks/i });
    await userEvent.click(increase);
    await userEvent.click(increase);
    await userEvent.click(screen.getByRole("button", { name: /^search$/i }));

    // Adding the stale option must record the ORIGINAL Jul 1–8 stay (7 nights),
    // not the failed 21-night criteria — the price was computed for July.
    await userEvent.click(await screen.findByRole("button", { name: /add to quote/i }));
    expect(await screen.findByText(/7 nights/i)).toBeInTheDocument();
  });

  it("stages a no-rate villa as a manual line and saves it with total, reason and currency", async () => {
    // Q-013: legacy NO RATE villas stay quotable with an operator-typed price.
    let quotationBody: Record<string, unknown> | null = null;
    server.use(
      http.get("/api/v1/properties", () => HttpResponse.json(drfPage([villaProperty]))),
      http.post("/api/v1/quotations:search-options", () =>
        HttpResponse.json({
          quotes: [
            {
              property_id: 7,
              available: false,
              error_code: "no_rate_available",
              error_detail: "No rate rule covers these dates.",
              currency_code: "EUR",
              hero_image_url: null,
            },
          ],
        }),
      ),
      http.get("/api/v1/terms-versions/current", () =>
        HttpResponse.json({ id: 5, version: "v1", is_current: true, published_at: null }),
      ),
      http.post("/api/v1/quotations", async ({ request }) => {
        quotationBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          { id: 50, reference: "QVC50", status: "draft", enquiry: 99 },
          { status: 201 },
        );
      }),
    );
    renderWithProviders(<QuoteBuilder enquiry={enquiry} />);

    await userEvent.click(await screen.findByRole("button", { name: /^search$/i }));
    // Flagged in the main list with the manual-add affordance.
    expect(await screen.findByText(/incomplete pricing/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /add manually/i }));

    // Staged manual + auto-expanded; commit blocked until total + reason filled.
    expect(screen.getByRole("button", { name: /save draft/i })).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/manual total/i), "5000");
    await userEvent.type(screen.getByLabelText(/reason for price override/i), "Priced by phone");
    await userEvent.click(screen.getByRole("button", { name: /save draft/i }));
    await userEvent.click(await screen.findByRole("button", { name: /^save quote$/i }));

    await waitFor(() => expect(quotationBody).not.toBeNull());
    const lines = quotationBody!.lines as Array<Record<string, unknown>>;
    expect(lines).toHaveLength(1);
    expect(lines[0]).toMatchObject({
      property: 7,
      is_manual: true,
      total: "5000.00",
      price_override_reason: "Priced by phone",
      currency: "EUR",
    });
  });

  it("stages a banded option carrying its occupancy bands (no single total, not manual)", async () => {
    // GAP-044: a result with ≥2 occupancy brackets stages as a banded line —
    // the shortlist renders the band rows rather than one headline total.
    server.use(
      http.get("/api/v1/properties", () => HttpResponse.json(drfPage([villaProperty]))),
      http.post("/api/v1/quotations:search-options", () =>
        HttpResponse.json({
          quotes: [
            {
              property_id: 7,
              available: true,
              currency_code: "USD",
              occupancy_bands: [
                { min_party: 1, max_party: 4, adults: 4, total: "4500.00", currency_code: "USD" },
                { min_party: 5, max_party: 8, adults: 8, total: "6200.00", currency_code: "USD" },
              ],
            },
          ],
        }),
      ),
    );
    renderWithProviders(<QuoteBuilder enquiry={enquiry} />);

    await userEvent.click(await screen.findByRole("button", { name: /^search$/i }));
    expect(await screen.findByText("Villa Sol")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /add to quote/i }));
    expect(await screen.findByText(/shortlist \(1\)/i)).toBeInTheDocument();

    // The shortlist renders both band prices (result card + shortlist row) and
    // never a summed villa total.
    expect(screen.getAllByText("$4,500.00").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("$6,200.00").length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText("$10,700.00")).not.toBeInTheDocument();

    // The staged line's manual toggle is disabled — bands are priced per bracket.
    await userEvent.click(screen.getByRole("button", { name: /edit line/i }));
    expect(screen.getByRole("checkbox", { name: /override the price manually/i })).toBeDisabled();
  });

  it("stages and saves a banded villa on a PICKED alternate week at that week's dates and bands (GAP-044b)", async () => {
    // GAP-044b two-axis picker end-to-end: a banded villa also offers a week
    // picker; picking an alternate week reprices to THAT week's bands, and the
    // saved lines carry the picked week's dates (not the criteria/default).
    let saveBody: { lines: Array<Record<string, unknown>> } | null = null;
    server.use(
      http.get("/api/v1/properties", () => HttpResponse.json(drfPage([villaProperty]))),
      http.get("/api/v1/terms-versions/current", () =>
        HttpResponse.json({ id: 5, version: "v1", is_current: true, published_at: null }),
      ),
      http.post("/api/v1/quotations", async ({ request }) => {
        saveBody = (await request.json()) as { lines: Array<Record<string, unknown>> };
        return HttpResponse.json(
          { id: 50, reference: "QVC50", status: "draft", enquiry: 99 },
          { status: 201 },
        );
      }),
      http.post("/api/v1/quotations:search-options", async ({ request }) => {
        const body = (await request.json()) as { flex_days: number };
        if (body.flex_days === 0) {
          // Reprice of the picked alternate week → that week's own bands.
          return HttpResponse.json({
            quotes: [
              {
                property_id: 7,
                available: true,
                currency_code: "USD",
                date_from: "2026-07-11",
                date_to: "2026-07-18",
                occupancy_bands: [
                  { min_party: 1, max_party: 4, adults: 4, total: "4800.00", currency_code: "USD" },
                  { min_party: 5, max_party: 8, adults: 8, total: "6600.00", currency_code: "USD" },
                ],
              },
            ],
          });
        }
        // The default-week search: banded villa with two changeover blocks.
        return HttpResponse.json({
          quotes: [
            {
              property_id: 7,
              available: true,
              currency_code: "USD",
              date_from: "2026-07-04",
              date_to: "2026-07-11",
              occupancy_bands: [
                { min_party: 1, max_party: 4, adults: 4, total: "4500.00", currency_code: "USD" },
                { min_party: 5, max_party: 8, adults: 8, total: "6200.00", currency_code: "USD" },
              ],
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
                  is_available: true,
                },
              ],
            },
          ],
        });
      }),
    );
    renderWithProviders(<QuoteBuilder enquiry={{ ...enquiry, flexibility_days: 2 }} />);

    await userEvent.click(await screen.findByRole("button", { name: /^search$/i }));
    await screen.findByText("Villa Sol");

    // Default week shows its bands; move to the alternate alone → its bands
    // reprice (uncheck the pre-checked default first).
    expect(screen.getAllByText("$4,500.00").length).toBeGreaterThan(0);
    const cells = within(screen.getByRole("group", { name: /stay options/i })).getAllByRole(
      "checkbox",
    );
    await userEvent.click(cells[0]);
    await userEvent.click(cells[1]);
    await screen.findByText("$4,800.00");

    await userEvent.click(screen.getByRole("button", { name: /add to quote/i }));
    expect(await screen.findByText(/shortlist \(1\)/i)).toBeInTheDocument();

    // Shortlist carries the PICKED week's dates and that week's band prices —
    // never a summed total (bands are alternatives), week fixed at Add.
    expect(screen.getByText(/11 Jul 2026 – 18 Jul 2026/)).toBeInTheDocument();
    expect(screen.getAllByText("$4,800.00").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("$6,600.00").length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText("$11,400.00")).not.toBeInTheDocument();

    // Save → one non-manual line per band at the PICKED week's dates + party.
    await userEvent.click(screen.getByRole("button", { name: /save draft/i }));
    await userEvent.click(await screen.findByRole("button", { name: /^save quote$/i }));
    await waitFor(() => expect(saveBody).not.toBeNull());
    expect(saveBody!.lines).toHaveLength(2);
    expect(saveBody!.lines[0]).toMatchObject({
      date_from: "2026-07-11",
      date_to: "2026-07-18",
      adults: 4,
      is_manual: false,
    });
    expect(saveBody!.lines[1]).toMatchObject({
      date_from: "2026-07-11",
      date_to: "2026-07-18",
      adults: 8,
      is_manual: false,
    });
  });

  it("runs save then opens the send-preview dialog for Send to guest", async () => {
    server.use(
      ...mockSaveFlow(),
      http.get("/api/v1/quotations/50:preview", () =>
        HttpResponse.json({
          html: "<p>Quote</p>",
          subject: "Your villa quote",
          intro: "Hello",
          signoff: "Regards",
        }),
      ),
    );
    renderWithProviders(<QuoteBuilder enquiry={enquiry} />);

    await userEvent.click(await screen.findByRole("button", { name: /^search$/i }));
    await userEvent.click(await screen.findByRole("button", { name: /add to quote/i }));

    // Send to guest → persists first via the save dialog…
    await userEvent.click(screen.getByRole("button", { name: /send to guest/i }));
    await userEvent.click(await screen.findByRole("button", { name: /^save quote$/i }));

    // …then opens the send-preview dialog on the saved quotation.
    expect(await screen.findByText(/send quotation to guest/i)).toBeInTheDocument();
  });
});
