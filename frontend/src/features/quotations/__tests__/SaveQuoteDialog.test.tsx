import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { drfPage } from "@/test/drf";
import { renderWithProviders } from "@/test/render";
import { SaveQuoteDialog } from "../components/SaveQuoteDialog";
import type { StagedLine } from "../schemas";
import type { EnquiryDetail } from "@/features/enquiries/schemas";

// Guest already attached so the save path skips guest creation.
const enquiry = {
  id: 99,
  reference: "ENQ-99",
  guest: 42,
  first_name: "Ada",
  last_name: "Lovelace",
  email: "ada@example.com",
} as unknown as EnquiryDetail;

// Requested 1–8 Jul, but the engine priced the changeover-day stay from 4 Jul.
const shiftedLine: StagedLine = {
  property_id: 7,
  property_name: "Villa Sol",
  hero_image_url: null,
  date_from: "2026-07-01",
  date_to: "2026-07-08",
  priced_date_from: "2026-07-04",
  priced_date_to: "2026-07-11",
  adults: 2,
  children: 0,
  total: "4500.00",
  is_manual: false,
  notes: "",
};

afterEach(() => server.resetHandlers());

describe("SaveQuoteDialog", () => {
  it("posts the operator's requested dates, leaving the backend as the single changeover shifter", async () => {
    let lineBody: Record<string, unknown> | null = null;
    server.use(
      http.get("/api/v1/currencies", () =>
        HttpResponse.json(drfPage([{ id: 1, code: "USD", name: "US Dollar", is_active: true }])),
      ),
      http.get("/api/v1/terms-versions/current", () =>
        HttpResponse.json({ id: 5, version: "v1", is_current: true, published_at: null }),
      ),
      http.post("/api/v1/quotations", () =>
        HttpResponse.json(
          { id: 50, reference: "Q-50", status: "draft", currency: "USD" },
          { status: 201 },
        ),
      ),
      http.post("/api/v1/quotations/50/lines", async ({ request }) => {
        lineBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 1 }, { status: 201 });
      }),
    );

    renderWithProviders(
      <SaveQuoteDialog
        open
        onOpenChange={() => undefined}
        enquiry={enquiry}
        lines={[shiftedLine]}
        currencyCode="USD"
        onCurrencyChange={() => undefined}
        onSaved={() => undefined}
      />,
    );

    await userEvent.click(await screen.findByRole("button", { name: /^save quote$/i }));

    await waitFor(() => expect(lineBody).not.toBeNull());
    // The requested dates go to the server, NOT the pre-shifted priced ones —
    // the backend re-derives and records the changeover shift on save.
    expect(lineBody).toMatchObject({
      property: 7,
      date_from: "2026-07-01",
      date_to: "2026-07-08",
    });
  });
});
