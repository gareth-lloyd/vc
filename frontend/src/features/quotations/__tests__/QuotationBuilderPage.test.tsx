import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { QuotationBuilderPage } from "../QuotationBuilderPage";

const enquiryFixture = {
  id: 99,
  reference: "ENQ-99",
  status: "new",
  guest: null,
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

describe("QuotationBuilderPage", () => {
  it("requires an enquiry query param", async () => {
    renderWithProviders(
      <Routes>
        <Route path="/quotations/new" element={<QuotationBuilderPage />} />
      </Routes>,
      { route: "/quotations/new" },
    );
    expect(await screen.findByText(/enquiry is required/i)).toBeInTheDocument();
  });

  it("prefills criteria from the enquiry", async () => {
    server.use(http.get("/api/v1/enquiries/99", () => HttpResponse.json(enquiryFixture)));
    renderWithProviders(
      <Routes>
        <Route path="/quotations/new" element={<QuotationBuilderPage />} />
      </Routes>,
      { route: "/quotations/new?enquiry=99" },
    );
    const dateFrom = await screen.findByLabelText(/^from$/i);
    expect(dateFrom).toHaveValue("2026-07-01");
    expect(screen.getByLabelText(/^to$/i)).toHaveValue("2026-07-08");
    expect(screen.getByLabelText(/adults/i)).toHaveValue(2);
  });

  it("shows priced options after a search", async () => {
    server.use(
      http.get("/api/v1/enquiries/99", () => HttpResponse.json(enquiryFixture)),
      http.get("/api/v1/properties", () =>
        HttpResponse.json({
          count: 1,
          next: null,
          previous: null,
          results: [{ id: 7, name: "Villa Sol", display_name: "Villa Sol", slug: "villa-sol" }],
        }),
      ),
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
    );
    renderWithProviders(
      <Routes>
        <Route path="/quotations/new" element={<QuotationBuilderPage />} />
      </Routes>,
      { route: "/quotations/new?enquiry=99" },
    );

    await userEvent.click(await screen.findByRole("button", { name: /search options/i }));
    expect(await screen.findByText("Villa Sol")).toBeInTheDocument();
    expect(screen.getByText(/USD 4500\.00/)).toBeInTheDocument();
  });
});
