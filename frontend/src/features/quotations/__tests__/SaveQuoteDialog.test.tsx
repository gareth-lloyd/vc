import { format } from "date-fns";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { formatDate } from "@/lib/format/date";
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
    manual_only: false,
    notes: "",
    ...overrides,
  };
}

// The save is ONE atomic POST: header + nested lines. Per-line assertions
// read `body.lines[i]`.
function mockSaveEndpoints(captureQuotationBody: (body: Record<string, unknown>) => void) {
  server.use(
    http.get("/api/v1/terms-versions/current", () =>
      HttpResponse.json({ id: 5, version: "v1", is_current: true, published_at: null }),
    ),
    http.post("/api/v1/quotations", async ({ request }) => {
      captureQuotationBody((await request.json()) as Record<string, unknown>);
      return HttpResponse.json({ id: 50, reference: "Q-50", status: "draft" }, { status: 201 });
    }),
  );
}

function linesOf(body: Record<string, unknown>): Record<string, unknown>[] {
  return body.lines as Record<string, unknown>[];
}

afterEach(() => server.resetHandlers());

describe("SaveQuoteDialog", () => {
  it("posts no header currency and pins each line's own priced currency", async () => {
    let quotationBody: Record<string, unknown> | null = null;
    mockSaveEndpoints((body) => {
      quotationBody = body;
    });

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

    await waitFor(() => expect(quotationBody).not.toBeNull());
    // Currency lives per line (GAP-014) — the header write carries none.
    expect(quotationBody).not.toHaveProperty("currency");
    expect(linesOf(quotationBody!)[0]).toMatchObject({ currency: "GBP" });
  });

  it("omits the line currency when the option priced without one", async () => {
    let quotationBody: Record<string, unknown> | null = null;
    mockSaveEndpoints((body) => {
      quotationBody = body;
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

    await waitFor(() => expect(quotationBody).not.toBeNull());
    expect(linesOf(quotationBody!)[0]).not.toHaveProperty("currency");
  });

  it("posts the operator's requested dates, leaving the backend as the single changeover shifter", async () => {
    let quotationBody: Record<string, unknown> | null = null;
    mockSaveEndpoints((body) => {
      quotationBody = body;
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

    await waitFor(() => expect(quotationBody).not.toBeNull());
    // The requested dates go to the server, NOT the pre-shifted priced ones —
    // the backend re-derives and records the changeover shift on save.
    expect(linesOf(quotationBody!)[0]).toMatchObject({
      property: 7,
      date_from: "2026-07-01",
      date_to: "2026-07-08",
    });
  });

  it("persists the per-line discount and inclusions instead of zeroing them", async () => {
    let quotationBody: Record<string, unknown> | null = null;
    mockSaveEndpoints((body) => {
      quotationBody = body;
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

    await waitFor(() => expect(quotationBody).not.toBeNull());
    const line = linesOf(quotationBody!)[0];
    // Regression: the builder used to hardcode discount "0" / inclusions "".
    expect(line).toMatchObject({
      discount: "150.00",
      inclusions: "Welcome hamper",
      is_manual: false,
    });
    // Non-manual lines omit the manual-only fields entirely.
    expect(line).not.toHaveProperty("total");
    expect(line).not.toHaveProperty("price_override_reason");
  });

  it("normalises a comma-typed discount to a canonical 2-dp decimal", async () => {
    let quotationBody: Record<string, unknown> | null = null;
    mockSaveEndpoints((body) => {
      quotationBody = body;
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

    await waitFor(() => expect(quotationBody).not.toBeNull());
    // The wire always gets "1000.00", never the raw "1,000" the user typed.
    expect(linesOf(quotationBody!)[0]).toMatchObject({ discount: "1000.00" });
  });

  it("never persists a discount on a manual line", async () => {
    let quotationBody: Record<string, unknown> | null = null;
    mockSaveEndpoints((body) => {
      quotationBody = body;
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

    await waitFor(() => expect(quotationBody).not.toBeNull());
    // Regression (#5): the server skips re-pricing manual lines, so a stale
    // discount would be stored yet never applied. Force it to "0".
    expect(linesOf(quotationBody!)[0]).toMatchObject({
      is_manual: true,
      discount: "0",
      total: "5000.00",
    });
  });

  it("sends total + reason for a manual-override line", async () => {
    let quotationBody: Record<string, unknown> | null = null;
    mockSaveEndpoints((body) => {
      quotationBody = body;
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

    await waitFor(() => expect(quotationBody).not.toBeNull());
    expect(linesOf(quotationBody!)[0]).toMatchObject({
      is_manual: true,
      total: "5000.00",
      price_override_reason: "Agreed rate",
    });
  });

  it("blocks save when a manual line is missing its total/reason", async () => {
    let quotationBody: Record<string, unknown> | null = null;
    mockSaveEndpoints((body) => {
      quotationBody = body;
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

    // The pre-save gate fires before the POST.
    expect(await screen.findByText(/missing its total or reason/i)).toBeInTheDocument();
    expect(quotationBody).toBeNull();
  });

  it("surfaces nested per-line server errors in the banner, not just 'Validation failed'", async () => {
    server.use(
      http.get("/api/v1/terms-versions/current", () =>
        HttpResponse.json({ id: 5, version: "v1", is_current: true, published_at: null }),
      ),
      http.post("/api/v1/quotations", () =>
        HttpResponse.json(
          {
            code: "validation_error",
            detail: "Validation failed",
            field_errors: {
              lines: [{}, { price_override_reason: ["This field is required for a manual line."] }],
            },
          },
          { status: 400 },
        ),
      ),
    );

    renderWithProviders(
      <SaveQuoteDialog
        open
        onOpenChange={() => undefined}
        enquiry={enquiry}
        lines={[stagedLine()]}
        onSaved={() => undefined}
      />,
    );

    await userEvent.click(await screen.findByRole("button", { name: /^save quote$/i }));

    expect(await screen.findByText(/required for a manual line/i)).toBeInTheDocument();
  });

  it("retries after a failed save without duplicating the created guest", async () => {
    let guestPosts = 0;
    let quotationPosts = 0;
    server.use(
      http.get("/api/v1/terms-versions/current", () =>
        HttpResponse.json({ id: 5, version: "v1", is_current: true, published_at: null }),
      ),
      http.post("/api/v1/guests", () => {
        guestPosts += 1;
        return HttpResponse.json(
          { id: 77, first_name: "Ada", last_name: "Lovelace", email: null },
          { status: 201 },
        );
      }),
      // First save attempt fails after the guest exists; the retry succeeds.
      http.post("/api/v1/quotations", () => {
        quotationPosts += 1;
        if (quotationPosts === 1) {
          return HttpResponse.json(
            { code: "validation_error", detail: "Boom", field_errors: {} },
            { status: 400 },
          );
        }
        return HttpResponse.json({ id: 50, reference: "Q-50", status: "draft" }, { status: 201 });
      }),
    );

    const unattached = {
      id: 99,
      reference: "ENQ-99",
      guest: null,
      first_name: "Ada",
      last_name: "Lovelace",
      email: "ada@example.com",
    } as unknown as EnquiryDetail;

    renderWithProviders(
      <SaveQuoteDialog
        open
        onOpenChange={() => undefined}
        enquiry={unattached}
        lines={[stagedLine()]}
        onSaved={() => undefined}
      />,
    );

    await userEvent.click(await screen.findByRole("button", { name: /^save quote$/i }));
    expect(await screen.findByText(/boom/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /^save quote$/i }));

    await waitFor(() => expect(quotationPosts).toBe(2));
    // The guest created on attempt #1 is reused, never duplicated.
    expect(guestPosts).toBe(1);
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

  // Expiry is LOCAL end-of-day semantics: the default and the input value are
  // both local wall-clock; only the wire format is UTC ISO. The old setUTC*
  // default + `.slice(0, 16)` display shifted the day in any non-UTC zone.
  it("defaults expiry to today+7 at 23:59 local", async () => {
    mockSaveEndpoints(() => undefined);
    renderWithProviders(
      <SaveQuoteDialog
        open
        onOpenChange={() => undefined}
        enquiry={enquiry}
        lines={[stagedLine()]}
        onSaved={() => undefined}
      />,
    );

    const expected = new Date();
    expected.setDate(expected.getDate() + 7);
    expected.setHours(23, 59, 59, 0);
    const input = await screen.findByLabelText<HTMLInputElement>(/expires/i);
    expect(input.value).toBe(format(expected, "yyyy-MM-dd'T'HH:mm"));
  });

  it("round-trips a picked local expiry: display stays put, wire is UTC ISO", async () => {
    let quotationBody: Record<string, unknown> | null = null;
    mockSaveEndpoints((body) => {
      quotationBody = body;
    });

    renderWithProviders(
      <SaveQuoteDialog
        open
        onOpenChange={() => undefined}
        enquiry={enquiry}
        lines={[stagedLine()]}
        onSaved={() => undefined}
      />,
    );

    const input = await screen.findByLabelText<HTMLInputElement>(/expires/i);
    fireEvent.change(input, { target: { value: "2026-06-25T23:59" } });
    // The displayed value must not drift to another day after the ISO round-trip.
    expect(input.value).toBe("2026-06-25T23:59");

    await userEvent.click(screen.getByRole("button", { name: /^save quote$/i }));
    await waitFor(() => expect(quotationBody).not.toBeNull());
    const wire = (quotationBody as unknown as { expires_at: string }).expires_at;
    expect(wire).toBe(new Date(2026, 5, 25, 23, 59).toISOString());
    // What detail pages render via formatDate matches what was picked.
    expect(formatDate(wire)).toBe("25 Jun 2026");
  });
});
