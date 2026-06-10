import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
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
  guest: 42,
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
  min_bedrooms: null,
  referral_code: "",
  inbound_message: "",
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
  return http.post("/api/v1/pricing:quote-bulk", async ({ request }) => {
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
    http.post("/api/v1/pricing:quote-bulk", () =>
      HttpResponse.json({
        quotes: [{ property_id: 7, available: true, total: "4500.00", currency_code: "USD" }],
      }),
    ),
    http.get("/api/v1/terms-versions/current", () =>
      HttpResponse.json({ id: 5, version: "v1", is_current: true, published_at: null }),
    ),
    http.post("/api/v1/quotations", () =>
      HttpResponse.json({ id: 50, reference: "QVC50", status: "draft" }, { status: 201 }),
    ),
    http.post("/api/v1/quotations/50/lines", () => HttpResponse.json({ id: 1 }, { status: 201 })),
  ];
}

function mockSearch() {
  return [
    http.get("/api/v1/properties", () => HttpResponse.json(drfPage([villaProperty]))),
    http.post("/api/v1/pricing:quote-bulk", () =>
      HttpResponse.json({
        quotes: [{ property_id: 7, available: true, total: "4500.00", currency_code: "USD" }],
      }),
    ),
  ];
}

beforeEach(() => {
  useAuthStore.setState({ role: "RESERVATIONS", isSuperuser: false, status: "authenticated" });
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

    await userEvent.click(await screen.findByRole("button", { name: /search options/i }));
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

  it("prefills criteria from the enquiry", async () => {
    renderWithProviders(<QuoteBuilder enquiry={enquiry} />);

    expect(await screen.findByLabelText(/^from$/i)).toHaveValue("2026-07-01");
    expect(screen.getByLabelText(/^to$/i)).toHaveValue("2026-07-08");
    expect(screen.getByLabelText(/adults/i)).toHaveValue(2);
  });

  it("searches without any currency selection and sends no currency to pricing", async () => {
    let bulkBody: Record<string, unknown> | null = null;
    server.use(
      http.get("/api/v1/properties", () => HttpResponse.json(drfPage([villaProperty]))),
      http.post("/api/v1/pricing:quote-bulk", async ({ request }) => {
        bulkBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          quotes: [{ property_id: 7, available: true, total: "4500.00", currency_code: "USD" }],
        });
      }),
    );
    renderWithProviders(<QuoteBuilder enquiry={enquiry} />);

    // No forced currency selection anywhere in the criteria pane (GAP-014).
    expect(screen.queryByRole("combobox", { name: /currency/i })).not.toBeInTheDocument();

    await userEvent.click(await screen.findByRole("button", { name: /search options/i }));
    expect(await screen.findByText("Villa Sol")).toBeInTheDocument();
    // Currency is an output of pricing, never an input to the search.
    await waitFor(() => expect(bulkBody).not.toBeNull());
    expect(bulkBody).not.toHaveProperty("currency");
  });

  it("renders mixed-currency results and cart lines each in their own currency", async () => {
    server.use(
      http.get("/api/v1/properties", () => HttpResponse.json(drfPage([villaProperty, villaTwo]))),
      http.post("/api/v1/pricing:quote-bulk", () =>
        HttpResponse.json({
          quotes: [
            { property_id: 7, available: true, total: "4500.00", currency_code: "GBP" },
            { property_id: 8, available: true, total: "5200.00", currency_code: "EUR" },
          ],
        }),
      ),
    );
    renderWithProviders(<QuoteBuilder enquiry={enquiry} />);

    await userEvent.click(await screen.findByRole("button", { name: /search options/i }));
    // One results list freely mixes currencies — each row prices in its own.
    expect(await screen.findByText("£4,500.00")).toBeInTheDocument();
    expect(screen.getByText("€5,200.00")).toBeInTheDocument();

    // Staged lines carry their own currency into the cart.
    const addButtons = screen.getAllByRole("button", { name: /add to quote/i });
    await userEvent.click(addButtons[0]);
    await userEvent.click(addButtons[1]);
    expect(await screen.findByText(/quote cart \(2\)/i)).toBeInTheDocument();
    expect(screen.getAllByText("£4,500.00")).toHaveLength(2); // result row + cart line
    expect(screen.getAllByText("€5,200.00")).toHaveLength(2);
  });

  it("adds a priced option into the cart", async () => {
    server.use(...mockSearch());
    renderWithProviders(<QuoteBuilder enquiry={enquiry} />);

    await userEvent.click(await screen.findByRole("button", { name: /search options/i }));
    expect(await screen.findByText("Villa Sol")).toBeInTheDocument();

    // The cart starts empty, then carries the added villa.
    expect(screen.getByText(/your cart is empty/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /add to quote/i }));
    expect(await screen.findByText(/quote cart \(1\)/i)).toBeInTheDocument();
    expect(screen.getByText(/7 nights/i)).toBeInTheDocument();
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

    await userEvent.click(await screen.findByRole("button", { name: /search options/i }));
    expect(await screen.findByText("Villa Sol")).toBeInTheDocument();
    // One of two matching villas priced so far.
    expect(screen.getByText(/priced 1 of 2 matching villas/i)).toBeInTheDocument();

    // Page 1 advertised more → Load more appends page 2 without dropping page 1.
    await userEvent.click(screen.getByRole("button", { name: /load more/i }));
    expect(await screen.findByText("Villa Luna")).toBeInTheDocument();
    expect(screen.getByText("Villa Sol")).toBeInTheDocument();
    // Last page reached → the button is gone.
    expect(screen.queryByRole("button", { name: /load more/i })).not.toBeInTheDocument();
  });

  it("does not advance the priced criteria when a re-search fails", async () => {
    // First search (Jul 1–8) succeeds; a re-search with an extended stay 500s.
    server.use(
      http.get("/api/v1/properties", () => HttpResponse.json(drfPage([villaProperty]))),
      http.post("/api/v1/pricing:quote-bulk", async ({ request }) => {
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

    await userEvent.click(await screen.findByRole("button", { name: /search options/i }));
    expect(await screen.findByText("Villa Sol")).toBeInTheDocument();

    // Extend the stay and re-search → the re-price 500s, leaving the original
    // results on screen.
    const to = screen.getByLabelText(/^to$/i);
    await userEvent.clear(to);
    await userEvent.type(to, "2026-07-22");
    await userEvent.click(screen.getByRole("button", { name: /search options/i }));

    // Adding the stale option must record the ORIGINAL Jul 1–8 stay (7 nights),
    // not the failed 21-night criteria — the price was computed for July.
    await userEvent.click(await screen.findByRole("button", { name: /add to quote/i }));
    expect(await screen.findByText(/7 nights/i)).toBeInTheDocument();
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

    await userEvent.click(await screen.findByRole("button", { name: /search options/i }));
    await userEvent.click(await screen.findByRole("button", { name: /add to quote/i }));

    // Send to guest → persists first via the save dialog…
    await userEvent.click(screen.getByRole("button", { name: /send to guest/i }));
    await userEvent.click(await screen.findByRole("button", { name: /^save quote$/i }));

    // …then opens the send-preview dialog on the saved quotation.
    expect(await screen.findByText(/send quotation to guest/i)).toBeInTheDocument();
  });
});
