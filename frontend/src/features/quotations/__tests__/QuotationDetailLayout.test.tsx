import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
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

const noLinesHandlers = [
  http.get("/api/v1/quotations/7", () => HttpResponse.json(baseQuotation)),
  http.get("/api/v1/quotations/7/lines", () =>
    HttpResponse.json({ count: 0, next: null, previous: null, results: [] }),
  ),
];

afterEach(() => {
  server.resetHandlers();
  useAuthStore.getState().clear();
});

function asReservationsUser() {
  // Only `role` and `isSuperuser` matter for `useHasReservationsRole` —
  // leave `user` null to avoid pinning the full UserMe shape in this test.
  useAuthStore.setState({
    role: "RESERVATIONS",
    isSuperuser: false,
    permissions: [],
    status: "authenticated",
    pendingTfa: null,
  });
}

function setup() {
  return renderWithProviders(
    <Routes>
      <Route path="/quotations/:id" element={<QuotationDetailLayout />} />
    </Routes>,
    { route: "/quotations/7" },
  );
}

describe("QuotationDetailLayout", () => {
  beforeEach(() => server.use(...noLinesHandlers));

  it("renders the reference and status badge", async () => {
    setup();
    await waitFor(() => expect(screen.getAllByText("Q-2026-007").length).toBeGreaterThan(0));
  });

  it("renders the empty lines state when there are no lines", async () => {
    setup();
    expect(await screen.findByText(/no lines yet/i)).toBeInTheDocument();
  });

  it("renders line rows when the lines endpoint returns data", async () => {
    server.resetHandlers();
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
    expect(screen.getByText(/€1,234\.50/)).toBeInTheDocument();
  });

  it("disables action buttons when the user lacks the reservations role", async () => {
    setup();
    const sendBtn = await screen.findByRole("button", { name: /send to guest/i });
    expect(sendBtn).toBeDisabled();
    expect(screen.getByRole("button", { name: /^duplicate$/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /convert to booking/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /withdraw/i })).toBeDisabled();
  });

  it("enables send/duplicate/withdraw with the reservations role; convert needs a sent quote with lines", async () => {
    asReservationsUser();
    setup();
    expect(await screen.findByRole("button", { name: /send to guest/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /^duplicate$/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /withdraw/i })).toBeEnabled();
    // Status=draft, so Convert is gated on "send the quote first".
    expect(screen.getByRole("button", { name: /convert to booking/i })).toBeDisabled();
  });

  it("enables convert once status is sent and lines exist", async () => {
    asReservationsUser();
    server.resetHandlers();
    server.use(
      http.get("/api/v1/quotations/7", () =>
        HttpResponse.json({ ...baseQuotation, status: "sent" }),
      ),
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
    // Wait for lines to load (button starts disabled with "no_lines" until
    // the list resolves; once data lands the disable_reason clears).
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /convert to booking/i })).toBeEnabled(),
    );
  });

  it("posts to :send on confirm", async () => {
    asReservationsUser();
    let sendCalled = false;
    server.use(
      http.post("/api/v1/quotations/7:send", () => {
        sendCalled = true;
        return HttpResponse.json({ ...baseQuotation, status: "sent" });
      }),
    );
    setup();
    await userEvent.click(await screen.findByRole("button", { name: /send to guest/i }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /mark sent/i }));
    await waitFor(() => expect(sendCalled).toBe(true));
  });

  it("posts to :withdraw with the captured reason", async () => {
    asReservationsUser();
    let captured: { reason?: string } = {};
    server.use(
      http.post("/api/v1/quotations/7:withdraw", async ({ request }) => {
        captured = (await request.json()) as { reason: string };
        return HttpResponse.json({ ...baseQuotation, status: "cancelled" });
      }),
    );
    setup();
    await userEvent.click(await screen.findByRole("button", { name: /withdraw/i }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(
      within(dialog).getByLabelText(/reason/i),
      "Quote superseded by a new option.",
    );
    await userEvent.click(within(dialog).getByRole("button", { name: /^withdraw$/i }));
    await waitFor(() => expect(captured.reason).toBe("Quote superseded by a new option."));
  });

  it("renders the not-found error on 404", async () => {
    server.resetHandlers();
    server.use(http.get("/api/v1/quotations/7", () => HttpResponse.json({}, { status: 404 })));
    setup();
    expect(await screen.findByText(/quotation not found/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
  });
});
