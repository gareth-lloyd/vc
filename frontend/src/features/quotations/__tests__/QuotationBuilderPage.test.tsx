import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { drfPage } from "@/test/drf";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import { QuotationBuilderPage } from "../QuotationBuilderPage";

const enquiryFixture = {
  id: 99,
  reference: "ENQ-99",
  status: "new",
  guest: 42,
  first_name: "Ada",
  last_name: "Lovelace",
  email: "ada@example.com",
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
};

const villaProperty = {
  id: 7,
  name: "Villa Sol",
  display_name: "Villa Sol",
  slug: "villa-sol",
  status: "active",
};

function mockCurrencies() {
  return http.get("/api/v1/currencies", () =>
    HttpResponse.json(drfPage([{ id: 1, code: "USD", name: "US Dollar", is_active: true }])),
  );
}

function mockSearch() {
  return [
    http.get("/api/v1/properties", () => HttpResponse.json(drfPage([villaProperty]))),
    http.post("/api/v1/pricing:quote-bulk", () =>
      HttpResponse.json({
        quotes: [
          {
            property_id: 7,
            available: true,
            total: "4500.00",
            currency_code: "USD",
            rate_subtotal: "4500.00",
          },
        ],
      }),
    ),
  ];
}

function renderBuilder(route = "/quotations/new?enquiry=99") {
  return renderWithProviders(
    <Routes>
      <Route path="/quotations/new" element={<QuotationBuilderPage />} />
      <Route path="/quotations/:id" element={<div>Quotation detail</div>} />
    </Routes>,
    { route },
  );
}

beforeEach(() => {
  useAuthStore.setState({ role: "RESERVATIONS", isSuperuser: false, status: "authenticated" });
  server.use(mockCurrencies());
});
afterEach(() => {
  useAuthStore.getState().clear();
  server.resetHandlers();
});

describe("QuotationBuilderPage", () => {
  it("requires an enquiry query param", async () => {
    renderBuilder("/quotations/new");
    expect(await screen.findByText(/enquiry is required/i)).toBeInTheDocument();
  });

  it("prefills criteria from the enquiry", async () => {
    server.use(http.get("/api/v1/enquiries/99", () => HttpResponse.json(enquiryFixture)));
    renderBuilder();
    const dateFrom = await screen.findByLabelText(/^from$/i);
    expect(dateFrom).toHaveValue("2026-07-01");
    expect(screen.getByLabelText(/^to$/i)).toHaveValue("2026-07-08");
    expect(screen.getByLabelText(/adults/i)).toHaveValue(2);
  });

  it("adds a priced option into the cart", async () => {
    server.use(
      http.get("/api/v1/enquiries/99", () => HttpResponse.json(enquiryFixture)),
      ...mockSearch(),
    );
    renderBuilder();

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
      http.get("/api/v1/enquiries/99", () => HttpResponse.json(enquiryFixture)),
      // Two active currencies so there's something to switch to.
      http.get("/api/v1/currencies", () =>
        HttpResponse.json(
          drfPage([
            { id: 1, code: "USD", name: "US Dollar", is_active: true },
            { id: 2, code: "EUR", name: "Euro", is_active: true },
          ]),
        ),
      ),
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
    renderBuilder();

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
    server.use(
      http.get("/api/v1/enquiries/99", () => HttpResponse.json(enquiryFixture)),
      http.get("/api/v1/currencies", () =>
        HttpResponse.json(
          drfPage([
            { id: 1, code: "USD", name: "US Dollar", is_active: true },
            { id: 2, code: "EUR", name: "Euro", is_active: true },
          ]),
        ),
      ),
      http.get("/api/v1/properties", () => HttpResponse.json(drfPage([villaProperty]))),
      http.post("/api/v1/pricing:quote-bulk", () =>
        HttpResponse.json({
          quotes: [{ property_id: 7, available: true, total: "4500.00", currency_code: "USD" }],
        }),
      ),
    );
    renderBuilder();

    await userEvent.click(await screen.findByRole("button", { name: /search options/i }));
    await userEvent.click(await screen.findByRole("button", { name: /add to quote/i }));
    expect(await screen.findByText(/quote cart \(1\)/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("combobox", { name: /currency/i }));
    await userEvent.click(await screen.findByRole("option", { name: /EUR/i }));

    // New-currency results landed → the stale-priced cart is cleared.
    expect(await screen.findByText(/your cart is empty/i)).toBeInTheDocument();
  });

  it("seeds the first active currency for a tenant without USD", async () => {
    server.use(
      http.get("/api/v1/enquiries/99", () => HttpResponse.json(enquiryFixture)),
      http.get("/api/v1/currencies", () =>
        HttpResponse.json(
          drfPage([
            { id: 2, code: "EUR", name: "Euro", is_active: true },
            { id: 3, code: "GBP", name: "Pound Sterling", is_active: true },
          ]),
        ),
      ),
    );
    renderBuilder();

    // The "USD" first-paint default isn't active here, so the picker reseeds to
    // the first active currency instead of dead-ending on a blank value.
    await screen.findByLabelText(/^from$/i);
    await waitFor(() =>
      expect(screen.getByRole("combobox", { name: /currency/i })).toHaveTextContent(/EUR/),
    );
  });

  it("runs save then opens the send-preview dialog for Send to guest", async () => {
    server.use(
      http.get("/api/v1/enquiries/99", () => HttpResponse.json(enquiryFixture)),
      ...mockSearch(),
      http.get("/api/v1/terms-versions/current", () =>
        HttpResponse.json({ id: 5, version: "v1", is_current: true, published_at: null }),
      ),
      http.post("/api/v1/quotations", () =>
        HttpResponse.json(
          { id: 50, reference: "Q-50", status: "draft", currency: "USD" },
          { status: 201 },
        ),
      ),
      http.post("/api/v1/quotations/50/lines", () => HttpResponse.json({ id: 1 }, { status: 201 })),
      http.get("/api/v1/quotations/50:preview", () =>
        HttpResponse.json({
          html: "<p>Quote</p>",
          subject: "Your villa quote",
          intro: "Hello",
          signoff: "Regards",
        }),
      ),
    );
    renderBuilder();

    await userEvent.click(await screen.findByRole("button", { name: /search options/i }));
    await userEvent.click(await screen.findByRole("button", { name: /add to quote/i }));

    // Send to guest → opens the save dialog.
    await userEvent.click(screen.getByRole("button", { name: /send to guest/i }));
    await userEvent.click(await screen.findByRole("button", { name: /^save quote$/i }));

    // After persisting, the send-preview dialog opens on the saved quotation.
    expect(await screen.findByText(/send quotation to guest/i)).toBeInTheDocument();
  });
});
