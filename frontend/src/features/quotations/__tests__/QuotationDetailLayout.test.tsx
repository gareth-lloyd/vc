import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { QuotationDetailLayout } from "../QuotationDetailLayout";

const baseQuotation = {
  id: 7,
  reference: "Q-2026-007",
  status: "draft",
  enquiry: 11,
  guest: 42,
  agent: null,
  currency: "EUR",
  expires_at: "2026-06-01T00:00:00Z",
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-01T00:00:00Z",
  cancel_reason: "",
  lines: [],
};

afterEach(() => {
  server.resetHandlers();
});

function setup() {
  return renderWithProviders(
    <Routes>
      <Route path="/quotations/:id" element={<QuotationDetailLayout />} />
    </Routes>,
    { route: "/quotations/7" },
  );
}

describe("QuotationDetailLayout", () => {
  it("renders the reference and status badge", async () => {
    server.use(
      http.get("/api/v1/quotations/7", () => HttpResponse.json(baseQuotation)),
      http.get("/api/v1/quotations/7/lines", () =>
        HttpResponse.json({ count: 0, next: null, previous: null, results: [] }),
      ),
    );
    setup();
    await waitFor(() => expect(screen.getAllByText("Q-2026-007").length).toBeGreaterThan(0));
  });

  it("renders the empty lines state when there are no lines", async () => {
    server.use(
      http.get("/api/v1/quotations/7", () => HttpResponse.json(baseQuotation)),
      http.get("/api/v1/quotations/7/lines", () =>
        HttpResponse.json({ count: 0, next: null, previous: null, results: [] }),
      ),
    );
    setup();
    expect(await screen.findByText(/no lines yet/i)).toBeInTheDocument();
  });

  it("renders line rows when the lines endpoint returns data", async () => {
    server.use(
      http.get("/api/v1/quotations/7", () => HttpResponse.json(baseQuotation)),
      http.get("/api/v1/quotations/7/lines", () =>
        HttpResponse.json({
          count: 1,
          next: null,
          previous: null,
          results: [
            {
              id: 33,
              quotation: 7,
              property: 12,
              date_from: "2026-07-01",
              date_to: "2026-07-08",
              adults: 2,
              children: 1,
              total: "1234.50",
              is_selected: true,
              is_manual: false,
              notes: "",
            },
          ],
        }),
      ),
    );
    setup();
    expect(await screen.findByText("#33")).toBeInTheDocument();
    expect(screen.getByText("#12")).toBeInTheDocument();
    expect(screen.getByText("1234.50")).toBeInTheDocument();
  });

  it("renders disabled action buttons with the coming-soon tooltip", async () => {
    server.use(
      http.get("/api/v1/quotations/7", () => HttpResponse.json(baseQuotation)),
      http.get("/api/v1/quotations/7/lines", () =>
        HttpResponse.json({ count: 0, next: null, previous: null, results: [] }),
      ),
    );
    setup();
    const sendBtn = await screen.findByRole("button", { name: /send to guest/i });
    expect(sendBtn).toBeDisabled();
    expect(screen.getByRole("button", { name: /duplicate/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /convert to booking/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /withdraw/i })).toBeDisabled();
  });

  it("renders the not-found error on 404", async () => {
    server.use(http.get("/api/v1/quotations/7", () => HttpResponse.json({}, { status: 404 })));
    setup();
    expect(await screen.findByText(/quotation not found/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
  });
});
