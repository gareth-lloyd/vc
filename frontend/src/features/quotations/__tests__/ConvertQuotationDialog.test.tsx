import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { ConvertQuotationDialog } from "../components/ConvertQuotationDialog";
import type { QuotationDetail } from "../schemas";

const quotation: QuotationDetail = {
  id: 7,
  reference: "Q-2026-007",
  status: "sent",
  enquiry: 11,
  guest: 42,
  agent: null,
  currency: "EUR",
  is_unbranded: false,
  terms_version: 1,
  expires_at: "2026-06-01T00:00:00Z",
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-01T00:00:00Z",
  cancel_reason: "",
  lines: [],
};

const lines = {
  count: 2,
  next: null,
  previous: null,
  results: [
    {
      id: 31,
      quotation: 7,
      property: 12,
      date_from: "2026-07-01",
      date_to: "2026-07-08",
      adults: 2,
      children: 0,
      total: "1200.00",
      is_selected: false,
      is_manual: false,
      notes: "",
    },
    {
      id: 32,
      quotation: 7,
      property: 14,
      date_from: "2026-07-15",
      date_to: "2026-07-22",
      adults: 4,
      children: 1,
      total: "2400.00",
      is_selected: true,
      is_manual: false,
      notes: "",
    },
  ],
};

const linesHandler = http.get("/api/v1/quotations/7/lines", () => HttpResponse.json(lines));

afterEach(() => server.resetHandlers());

function setup() {
  return renderWithProviders(
    <Routes>
      <Route
        path="/quotations/:id"
        element={
          <ConvertQuotationDialog open onOpenChange={() => undefined} quotation={quotation} />
        }
      />
      <Route path="/bookings/:id" element={<div data-testid="booking-page">landed</div>} />
    </Routes>,
    { route: "/quotations/7" },
  );
}

describe("ConvertQuotationDialog", () => {
  beforeEach(() => server.use(linesHandler));

  it("renders the lines and defaults to the selected one", async () => {
    setup();
    expect(await screen.findByLabelText(/property #12/i)).not.toBeChecked();
    expect(await screen.findByLabelText(/property #14/i)).toBeChecked();
  });

  it("posts the chosen line + payment method and navigates to the new booking", async () => {
    let capturedBody: Record<string, unknown> | null = null;
    server.use(
      linesHandler,
      http.post("/api/v1/quotations/7:convert", async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          {
            id: 99,
            reference: "BK-99",
            status: "awaiting_deposit",
            property: 12,
            guest: 42,
            date_from: "2026-07-01",
            date_to: "2026-07-08",
            adults: 2,
            children: 0,
            currency: 1,
            rental_price: "1200.00",
            balance_due: "1200.00",
            site_source: "main_website",
          },
          { status: 201 },
        );
      }),
    );

    setup();
    await userEvent.click(await screen.findByLabelText(/property #12/i));
    await userEvent.click(screen.getByRole("button", { name: /^convert to booking$/i }));

    await waitFor(() => expect(capturedBody).not.toBeNull());
    expect(capturedBody).toEqual({
      line: 31,
      payment_method: "card",
    });
    expect(await screen.findByTestId("booking-page")).toBeInTheDocument();
  });

  it("renders the changeover shift note for a line whose arrival was moved", async () => {
    server.use(
      http.get("/api/v1/quotations/7/lines", () =>
        HttpResponse.json({
          count: 1,
          next: null,
          previous: null,
          results: [
            {
              id: 31,
              quotation: 7,
              property: 12,
              // Engine nudged the arrival forward from 1 Jul to the changeover day.
              date_from: "2026-07-04",
              date_to: "2026-07-11",
              changeover_shifted_from: "2026-07-01",
              adults: 2,
              children: 0,
              total: "1200.00",
              is_selected: true,
              is_manual: false,
              notes: "",
            },
          ],
        }),
      ),
    );

    setup();
    expect(
      await screen.findByText(/arrival moved from .+ to the property's changeover day/i),
    ).toBeInTheDocument();
  });

  it("does not render a shift note for a line whose dates weren't moved", async () => {
    setup();
    // Both fixture lines have no `changeover_shifted_from`.
    await screen.findByLabelText(/property #12/i);
    expect(
      screen.queryByText(/moved from .+ to the property's changeover day/i),
    ).not.toBeInTheDocument();
  });

  it("renders a generic inline error for non-changeover 4xx", async () => {
    server.use(
      linesHandler,
      http.post("/api/v1/quotations/7:convert", () =>
        HttpResponse.json(
          {
            code: "invalid_transition",
            detail: "Quotation must be sent first.",
            field_errors: {},
          },
          { status: 409 },
        ),
      ),
    );

    setup();
    await userEvent.click(await screen.findByRole("button", { name: /^convert to booking$/i }));
    const alerts = await screen.findAllByRole("alert");
    expect(
      alerts.some((node) => /quotation must be sent first/i.test(node.textContent ?? "")),
    ).toBe(true);
  });

  it("disables submit while the lines list is empty", async () => {
    server.use(
      http.get("/api/v1/quotations/7/lines", () =>
        HttpResponse.json({ count: 0, next: null, previous: null, results: [] }),
      ),
    );
    setup();
    expect(await screen.findByText(/this quote has no lines yet/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^convert to booking$/i })).toBeDisabled();
  });
});
