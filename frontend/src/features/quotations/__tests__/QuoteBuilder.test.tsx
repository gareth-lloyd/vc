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

function mockSaveFlow() {
  return [
    http.get("/api/v1/currencies", () =>
      HttpResponse.json(drfPage([{ id: 1, code: "USD", name: "US Dollar", is_active: true }])),
    ),
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
      HttpResponse.json(
        { id: 50, reference: "QVC50", status: "draft", currency: "USD" },
        { status: 201 },
      ),
    ),
    http.post("/api/v1/quotations/50/lines", () => HttpResponse.json({ id: 1 }, { status: 201 })),
  ];
}

function mockCurrencies(codes: Array<{ id: number; code: string; name: string }>) {
  return http.get("/api/v1/currencies", () =>
    HttpResponse.json(drfPage(codes.map((c) => ({ ...c, is_active: true })))),
  );
}

const USD = { id: 1, code: "USD", name: "US Dollar" };
const EUR = { id: 2, code: "EUR", name: "Euro" };
const GBP = { id: 3, code: "GBP", name: "Pound Sterling" };

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
    server.use(mockCurrencies([USD]));
    renderWithProviders(<QuoteBuilder enquiry={enquiry} />);

    expect(await screen.findByLabelText(/^from$/i)).toHaveValue("2026-07-01");
    expect(screen.getByLabelText(/^to$/i)).toHaveValue("2026-07-08");
    expect(screen.getByLabelText(/adults/i)).toHaveValue(2);
  });

  it("adds a priced option into the cart", async () => {
    server.use(mockCurrencies([USD]), ...mockSearch());
    renderWithProviders(<QuoteBuilder enquiry={enquiry} />);

    await userEvent.click(await screen.findByRole("button", { name: /search options/i }));
    expect(await screen.findByText("Villa Sol")).toBeInTheDocument();

    // The cart starts empty, then carries the added villa.
    expect(screen.getByText(/your cart is empty/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /add to quote/i }));
    expect(await screen.findByText(/quote cart \(1\)/i)).toBeInTheDocument();
    expect(screen.getByText(/7 nights/i)).toBeInTheDocument();
  });

  it("keeps the cart and reverts the picker when a currency re-search fails", async () => {
    server.use(
      mockCurrencies([USD, EUR]),
      http.get("/api/v1/properties", () => HttpResponse.json(drfPage([villaProperty]))),
      // The re-price in EUR fails; the USD search succeeds.
      http.post("/api/v1/pricing:quote-bulk", async ({ request }) => {
        const body = (await request.json()) as { currency: string };
        if (body.currency === "EUR") return new HttpResponse(null, { status: 500 });
        return HttpResponse.json({
          quotes: [{ property_id: 7, available: true, total: "4500.00", currency_code: "USD" }],
        });
      }),
    );
    renderWithProviders(<QuoteBuilder enquiry={enquiry} />);

    await userEvent.click(await screen.findByRole("button", { name: /search options/i }));
    await userEvent.click(await screen.findByRole("button", { name: /add to quote/i }));
    expect(await screen.findByText(/quote cart \(1\)/i)).toBeInTheDocument();

    // Switch to EUR — the re-search 500s, so the cart must survive.
    await userEvent.click(screen.getByRole("combobox", { name: /currency/i }));
    await userEvent.click(await screen.findByRole("option", { name: /EUR/i }));

    expect(await screen.findByText(/quote cart \(1\)/i)).toBeInTheDocument();
    // Picker reverts to the currency the cart is actually priced in.
    expect(screen.getByRole("combobox", { name: /currency/i })).toHaveTextContent(/USD/);
  });

  it("clears the cart when a currency re-search succeeds", async () => {
    server.use(mockCurrencies([USD, EUR]), ...mockSearch());
    renderWithProviders(<QuoteBuilder enquiry={enquiry} />);

    await userEvent.click(await screen.findByRole("button", { name: /search options/i }));
    await userEvent.click(await screen.findByRole("button", { name: /add to quote/i }));
    expect(await screen.findByText(/quote cart \(1\)/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("combobox", { name: /currency/i }));
    await userEvent.click(await screen.findByRole("option", { name: /EUR/i }));

    // New-currency results landed → the stale-priced cart is cleared.
    expect(await screen.findByText(/your cart is empty/i)).toBeInTheDocument();
  });

  it("seeds the first active currency for a tenant without USD", async () => {
    server.use(mockCurrencies([EUR, GBP]));
    renderWithProviders(<QuoteBuilder enquiry={enquiry} />);

    // The empty first-paint currency reseeds to the first active code instead
    // of dead-ending on a blank value the picker can't bind.
    await screen.findByLabelText(/^from$/i);
    await waitFor(() =>
      expect(screen.getByRole("combobox", { name: /currency/i })).toHaveTextContent(/EUR/),
    );
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
