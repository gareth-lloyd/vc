import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
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

function stagedLine(overrides: Partial<StagedLine> = {}): StagedLine {
  return {
    property_id: 7,
    property_name: "Villa Sol",
    hero_image_url: null,
    date_from: "2026-07-01",
    date_to: "2026-07-08",
    priced_date_from: "2026-07-01",
    priced_date_to: "2026-07-08",
    adults: 2,
    children: 0,
    currency: "USD",
    total: "4500.00",
    discount: "0",
    inclusions: "",
    price_override_reason: "",
    is_manual: false,
    notes: "",
    ...overrides,
  };
}

function mockSaveEndpoints(
  captureLineBody: (body: Record<string, unknown>) => void,
  captureQuotationBody?: (body: Record<string, unknown>) => void,
) {
  server.use(
    http.get("/api/v1/terms-versions/current", () =>
      HttpResponse.json({ id: 5, version: "v1", is_current: true, published_at: null }),
    ),
    http.post("/api/v1/quotations", async ({ request }) => {
      captureQuotationBody?.((await request.json()) as Record<string, unknown>);
      return HttpResponse.json({ id: 50, reference: "Q-50", status: "draft" }, { status: 201 });
    }),
    http.post("/api/v1/quotations/50/lines", async ({ request }) => {
      captureLineBody((await request.json()) as Record<string, unknown>);
      return HttpResponse.json({ id: 1 }, { status: 201 });
    }),
  );
}

afterEach(() => server.resetHandlers());

describe("SaveQuoteDialog", () => {
  it("posts no header currency and pins each line's own priced currency", async () => {
    let lineBody: Record<string, unknown> | null = null;
    let quotationBody: Record<string, unknown> | null = null;
    mockSaveEndpoints(
      (body) => {
        lineBody = body;
      },
      (body) => {
        quotationBody = body;
      },
    );

    renderWithProviders(
      <SaveQuoteDialog
        open
        onOpenChange={() => undefined}
        enquiry={enquiry}
        lines={[stagedLine({ currency: "GBP" })]}
        onSaved={() => undefined}
      />,
    );

    await userEvent.click(await screen.findByRole("button", { name: /^save quote$/i }));

    await waitFor(() => expect(lineBody).not.toBeNull());
    // Currency lives per line (GAP-014) — the header write carries none.
    expect(quotationBody).not.toHaveProperty("currency");
    expect(lineBody).toMatchObject({ currency: "GBP" });
  });

  it("omits the line currency when the option priced without one", async () => {
    let lineBody: Record<string, unknown> | null = null;
    mockSaveEndpoints((body) => {
      lineBody = body;
    });

    // A manual line staged from an unpriceable option carries no currency —
    // the backend resolves its canonical per-property default.
    renderWithProviders(
      <SaveQuoteDialog
        open
        onOpenChange={() => undefined}
        enquiry={enquiry}
        lines={[
          stagedLine({
            currency: null,
            is_manual: true,
            total: "5000.00",
            price_override_reason: "Agreed rate",
          }),
        ]}
        onSaved={() => undefined}
      />,
    );

    await userEvent.click(await screen.findByRole("button", { name: /^save quote$/i }));

    await waitFor(() => expect(lineBody).not.toBeNull());
    expect(lineBody).not.toHaveProperty("currency");
  });

  it("posts the operator's requested dates, leaving the backend as the single changeover shifter", async () => {
    let lineBody: Record<string, unknown> | null = null;
    mockSaveEndpoints((body) => {
      lineBody = body;
    });

    // Requested 1–8 Jul, but the engine priced the changeover-day stay from 4 Jul.
    renderWithProviders(
      <SaveQuoteDialog
        open
        onOpenChange={() => undefined}
        enquiry={enquiry}
        lines={[stagedLine({ priced_date_from: "2026-07-04", priced_date_to: "2026-07-11" })]}
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

  it("persists the per-line discount and inclusions instead of zeroing them", async () => {
    let lineBody: Record<string, unknown> | null = null;
    mockSaveEndpoints((body) => {
      lineBody = body;
    });

    renderWithProviders(
      <SaveQuoteDialog
        open
        onOpenChange={() => undefined}
        enquiry={enquiry}
        lines={[stagedLine({ discount: "150.00", inclusions: "Welcome hamper" })]}
        onSaved={() => undefined}
      />,
    );

    await userEvent.click(await screen.findByRole("button", { name: /^save quote$/i }));

    await waitFor(() => expect(lineBody).not.toBeNull());
    // Regression: the builder used to hardcode discount "0" / inclusions "".
    expect(lineBody).toMatchObject({
      discount: "150.00",
      inclusions: "Welcome hamper",
      is_manual: false,
    });
    // Non-manual lines omit the manual-only fields entirely.
    expect(lineBody).not.toHaveProperty("total");
    expect(lineBody).not.toHaveProperty("price_override_reason");
  });

  it("normalises a comma-typed discount to a canonical 2-dp decimal", async () => {
    let lineBody: Record<string, unknown> | null = null;
    mockSaveEndpoints((body) => {
      lineBody = body;
    });

    renderWithProviders(
      <SaveQuoteDialog
        open
        onOpenChange={() => undefined}
        enquiry={enquiry}
        lines={[stagedLine({ discount: "1,000" })]}
        onSaved={() => undefined}
      />,
    );

    await userEvent.click(await screen.findByRole("button", { name: /^save quote$/i }));

    await waitFor(() => expect(lineBody).not.toBeNull());
    // The wire always gets "1000.00", never the raw "1,000" the user typed.
    expect(lineBody).toMatchObject({ discount: "1000.00" });
  });

  it("never persists a discount on a manual line", async () => {
    let lineBody: Record<string, unknown> | null = null;
    mockSaveEndpoints((body) => {
      lineBody = body;
    });

    // A discount was typed before the operator toggled the line to manual.
    renderWithProviders(
      <SaveQuoteDialog
        open
        onOpenChange={() => undefined}
        enquiry={enquiry}
        lines={[
          stagedLine({
            is_manual: true,
            discount: "150.00",
            total: "5000.00",
            price_override_reason: "Agreed rate",
          }),
        ]}
        onSaved={() => undefined}
      />,
    );

    await userEvent.click(await screen.findByRole("button", { name: /^save quote$/i }));

    await waitFor(() => expect(lineBody).not.toBeNull());
    // Regression (#5): the server skips re-pricing manual lines, so a stale
    // discount would be stored yet never applied. Force it to "0".
    expect(lineBody).toMatchObject({ is_manual: true, discount: "0", total: "5000.00" });
  });

  it("sends total + reason for a manual-override line", async () => {
    let lineBody: Record<string, unknown> | null = null;
    mockSaveEndpoints((body) => {
      lineBody = body;
    });

    renderWithProviders(
      <SaveQuoteDialog
        open
        onOpenChange={() => undefined}
        enquiry={enquiry}
        lines={[
          stagedLine({
            is_manual: true,
            total: "5000.00",
            price_override_reason: "Agreed rate",
          }),
        ]}
        onSaved={() => undefined}
      />,
    );

    await userEvent.click(await screen.findByRole("button", { name: /^save quote$/i }));

    await waitFor(() => expect(lineBody).not.toBeNull());
    expect(lineBody).toMatchObject({
      is_manual: true,
      total: "5000.00",
      price_override_reason: "Agreed rate",
    });
  });

  it("blocks save when a manual line is missing its total/reason", async () => {
    let lineBody: Record<string, unknown> | null = null;
    mockSaveEndpoints((body) => {
      lineBody = body;
    });

    renderWithProviders(
      <SaveQuoteDialog
        open
        onOpenChange={() => undefined}
        enquiry={enquiry}
        lines={[stagedLine({ is_manual: true, total: "", price_override_reason: "" })]}
        onSaved={() => undefined}
      />,
    );

    await userEvent.click(await screen.findByRole("button", { name: /^save quote$/i }));

    // The pre-save gate fires before any line POST.
    expect(await screen.findByText(/missing its total or reason/i)).toBeInTheDocument();
    expect(lineBody).toBeNull();
  });

  it("passes the enquiry's phone through and never fabricates a synthetic email", async () => {
    let guestBody: Record<string, unknown> | null = null;
    server.use(
      http.get("/api/v1/terms-versions/current", () =>
        HttpResponse.json({ id: 5, version: "v1", is_current: true, published_at: null }),
      ),
      http.post("/api/v1/guests", async ({ request }) => {
        guestBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          { id: 77, first_name: "Ada", last_name: "Lovelace", email: null },
          { status: 201 },
        );
      }),
      http.post("/api/v1/quotations", () =>
        HttpResponse.json({ id: 50, reference: "Q-50", status: "draft" }, { status: 201 }),
      ),
      http.post("/api/v1/quotations/50/lines", () => HttpResponse.json({ id: 1 }, { status: 201 })),
    );

    // Unattached, phone-only enquiry (no email captured at lead time).
    const phoneOnly = {
      id: 99,
      reference: "ENQ-99",
      guest: null,
      first_name: "Ada",
      last_name: "Lovelace",
      email: "",
      phone: "+447911123456",
    } as unknown as EnquiryDetail;

    renderWithProviders(
      <SaveQuoteDialog
        open
        onOpenChange={() => undefined}
        enquiry={phoneOnly}
        lines={[stagedLine()]}
        onSaved={() => undefined}
      />,
    );

    await userEvent.click(await screen.findByRole("button", { name: /^save quote$/i }));

    await waitFor(() => expect(guestBody).not.toBeNull());
    expect(guestBody).toMatchObject({
      first_name: "Ada",
      last_name: "Lovelace",
      phone: "+447911123456",
    });
    // No synthetic `enquiry-{id}@noemail.local` — email omitted entirely.
    expect(guestBody).not.toHaveProperty("email");
  });

  it("blocks the save when an unattached enquiry has neither email nor phone", async () => {
    let guestPosted = false;
    server.use(
      http.get("/api/v1/terms-versions/current", () =>
        HttpResponse.json({ id: 5, version: "v1", is_current: true, published_at: null }),
      ),
      http.post("/api/v1/guests", () => {
        guestPosted = true;
        return HttpResponse.json(
          { id: 77, first_name: "X", last_name: "Y", email: null },
          { status: 201 },
        );
      }),
    );

    const noChannel = {
      id: 99,
      reference: "ENQ-99",
      guest: null,
      first_name: "Ada",
      last_name: "Lovelace",
      email: "",
      phone: "",
    } as unknown as EnquiryDetail;

    renderWithProviders(
      <SaveQuoteDialog
        open
        onOpenChange={() => undefined}
        enquiry={noChannel}
        lines={[stagedLine()]}
        onSaved={() => undefined}
      />,
    );

    await userEvent.click(await screen.findByRole("button", { name: /^save quote$/i }));

    expect(await screen.findByText(/no email or phone/i)).toBeInTheDocument();
    expect(guestPosted).toBe(false);
  });

  function mockGuestCreate(capture: (body: Record<string, unknown>) => void) {
    server.use(
      http.get("/api/v1/terms-versions/current", () =>
        HttpResponse.json({ id: 5, version: "v1", is_current: true, published_at: null }),
      ),
      http.post("/api/v1/guests", async ({ request }) => {
        capture((await request.json()) as Record<string, unknown>);
        return HttpResponse.json(
          { id: 77, first_name: "Ada", last_name: "Lovelace", email: null },
          { status: 201 },
        );
      }),
      http.post("/api/v1/quotations", () =>
        HttpResponse.json({ id: 50, reference: "Q-50", status: "draft" }, { status: 201 }),
      ),
      http.post("/api/v1/quotations/50/lines", () => HttpResponse.json({ id: 1 }, { status: 201 })),
    );
  }

  it("carries the enquiry's contact_method when its channel is present", async () => {
    let guestBody: Record<string, unknown> | null = null;
    mockGuestCreate((body) => {
      guestBody = body;
    });

    // Phone-only enquiry that prefers SMS — the phone channel backs the pref.
    const smsEnquiry = {
      id: 99,
      reference: "ENQ-99",
      guest: null,
      first_name: "Ada",
      last_name: "Lovelace",
      email: "",
      phone: "+447911123456",
      contact_method: "sms",
    } as unknown as EnquiryDetail;

    renderWithProviders(
      <SaveQuoteDialog
        open
        onOpenChange={() => undefined}
        enquiry={smsEnquiry}
        lines={[stagedLine()]}
        onSaved={() => undefined}
      />,
    );

    await userEvent.click(await screen.findByRole("button", { name: /^save quote$/i }));

    await waitFor(() => expect(guestBody).not.toBeNull());
    expect(guestBody).toMatchObject({ phone: "+447911123456", contact_method: "sms" });
  });

  it("drops the contact_method when its required channel is missing", async () => {
    let guestBody: Record<string, unknown> | null = null;
    mockGuestCreate((body) => {
      guestBody = body;
    });

    // Prefers email, but only a phone was captured — forwarding "email" would
    // 400 on the server's contactability CHECK, so the guard omits it.
    const mismatched = {
      id: 99,
      reference: "ENQ-99",
      guest: null,
      first_name: "Ada",
      last_name: "Lovelace",
      email: "",
      phone: "+447911123456",
      contact_method: "email",
    } as unknown as EnquiryDetail;

    renderWithProviders(
      <SaveQuoteDialog
        open
        onOpenChange={() => undefined}
        enquiry={mismatched}
        lines={[stagedLine()]}
        onSaved={() => undefined}
      />,
    );

    await userEvent.click(await screen.findByRole("button", { name: /^save quote$/i }));

    await waitFor(() => expect(guestBody).not.toBeNull());
    expect(guestBody).toMatchObject({ phone: "+447911123456" });
    expect(guestBody).not.toHaveProperty("contact_method");
  });
});
