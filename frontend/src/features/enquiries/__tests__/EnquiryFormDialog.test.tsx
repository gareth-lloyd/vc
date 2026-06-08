import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { EnquiryFormDialog } from "../components/EnquiryFormDialog";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

afterEach(() => {
  server.resetHandlers();
});

const VALID_GUEST: Record<string, unknown> = {
  first_name: "Ada",
  last_name: "Lovelace",
  email: "ada@example.com",
  phone: "",
  adults: 2,
  children: 0,
  min_bedrooms: null,
  request_type: "quote",
  site_source: "main_website",
  inbound_message: "",
  is_flexible: false,
};

describe("EnquiryFormDialog date-spread stepper", () => {
  beforeEach(() => {
    // no-op
  });

  it("submits the operator-entered dates unchanged when spread is 0", async () => {
    let payload: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/enquiries", async ({ request }) => {
        payload = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          {
            id: 1,
            reference: "E-001",
            status: "new",
            ...VALID_GUEST,
            date_from: payload.date_from,
            date_to: payload.date_to,
            adults: 2,
            children: 0,
            request_type: "quote",
            site_source: "main_website",
            is_flexible: false,
            min_bedrooms: null,
            referral_code: "",
            inbound_message: "",
          },
          { status: 201 },
        );
      }),
    );

    renderWithProviders(<EnquiryFormDialog mode="create" open onOpenChange={() => {}} />);

    await userEvent.type(screen.getByLabelText(/first name/i), "Ada");
    await userEvent.type(screen.getByLabelText(/last name/i), "Lovelace");
    await userEvent.type(screen.getByLabelText(/email/i), "ada@example.com");
    await userEvent.clear(screen.getByLabelText(/^from$/i));
    await userEvent.type(screen.getByLabelText(/^from$/i), "2026-06-10");
    await userEvent.clear(screen.getByLabelText(/^to$/i));
    await userEvent.type(screen.getByLabelText(/^to$/i), "2026-06-17");

    await userEvent.click(screen.getByRole("button", { name: /create/i }));

    await waitFor(() => expect(payload).not.toBeNull());
    expect(payload).toMatchObject({ date_from: "2026-06-10", date_to: "2026-06-17" });
  });

  it("widens date_from / date_to by the configured spread", async () => {
    let payload: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/enquiries", async ({ request }) => {
        payload = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          {
            id: 2,
            reference: "E-002",
            status: "new",
            ...VALID_GUEST,
            date_from: payload.date_from,
            date_to: payload.date_to,
            adults: 2,
            children: 0,
            request_type: "quote",
            site_source: "main_website",
            is_flexible: false,
            min_bedrooms: null,
            referral_code: "",
            inbound_message: "",
          },
          { status: 201 },
        );
      }),
    );

    renderWithProviders(<EnquiryFormDialog mode="create" open onOpenChange={() => {}} />);

    await userEvent.type(screen.getByLabelText(/first name/i), "Ada");
    await userEvent.type(screen.getByLabelText(/last name/i), "Lovelace");
    await userEvent.type(screen.getByLabelText(/email/i), "ada@example.com");
    await userEvent.clear(screen.getByLabelText(/^from$/i));
    await userEvent.type(screen.getByLabelText(/^from$/i), "2026-06-10");
    await userEvent.clear(screen.getByLabelText(/^to$/i));
    await userEvent.type(screen.getByLabelText(/^to$/i), "2026-06-17");

    // Click the "+" stepper twice to widen by ±2 days.
    const increment = screen.getByRole("button", { name: /increase date spread/i });
    await userEvent.click(increment);
    await userEvent.click(increment);

    // Widened preview reflects the new range.
    expect(screen.getByText(/2026-06-08/)).toBeInTheDocument();
    expect(screen.getByText(/2026-06-19/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /create/i }));

    await waitFor(() => expect(payload).not.toBeNull());
    expect(payload).toMatchObject({ date_from: "2026-06-08", date_to: "2026-06-19" });
  });

  it("shows preview_zero text when both dates are set and spread is 0", async () => {
    renderWithProviders(<EnquiryFormDialog mode="create" open onOpenChange={() => {}} />);

    await userEvent.clear(screen.getByLabelText(/^from$/i));
    await userEvent.type(screen.getByLabelText(/^from$/i), "2026-06-10");
    await userEvent.clear(screen.getByLabelText(/^to$/i));
    await userEvent.type(screen.getByLabelText(/^to$/i), "2026-06-17");

    // Spread stays at 0 by default — the more-informative preview_zero copy
    // should appear instead of the generic flexibility hint.
    expect(screen.getByText(/submitting requested dates unchanged/i)).toBeInTheDocument();
    expect(
      screen.queryByText(/guests are often flexible around changeover/i),
    ).not.toBeInTheDocument();
  });

  it("clamps spread at the maximum and minimum", async () => {
    renderWithProviders(<EnquiryFormDialog mode="create" open onOpenChange={() => {}} />);

    const increment = screen.getByRole("button", { name: /increase date spread/i });
    const decrement = screen.getByRole("button", { name: /decrease date spread/i });

    // Start at 0 — decrement should not go negative.
    expect(decrement).toBeDisabled();

    // Increment up to the cap (3).
    await userEvent.click(increment);
    await userEvent.click(increment);
    await userEvent.click(increment);
    expect(increment).toBeDisabled();
    expect(screen.getByText(/±\s*3\s*days/i)).toBeInTheDocument();
  });
});

describe("EnquiryFormDialog phone + contact_method capture", () => {
  it("persists the typed phone and chosen contact method on create", async () => {
    let payload: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/enquiries", async ({ request }) => {
        payload = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          { id: 3, reference: "E-003", status: "new", ...VALID_GUEST, ...payload },
          { status: 201 },
        );
      }),
    );

    renderWithProviders(<EnquiryFormDialog mode="create" open onOpenChange={() => {}} />);

    await userEvent.type(screen.getByLabelText(/first name/i), "Ada");
    await userEvent.type(screen.getByLabelText(/last name/i), "Lovelace");
    await userEvent.type(screen.getByLabelText(/email/i), "ada@example.com");
    await userEvent.type(screen.getByLabelText(/^phone$/i), "+447911123456");

    await userEvent.click(screen.getByRole("combobox", { name: /preferred contact method/i }));
    await userEvent.click(await screen.findByRole("option", { name: "Phone" }));

    await userEvent.click(screen.getByRole("button", { name: /create/i }));

    await waitFor(() => expect(payload).not.toBeNull());
    expect(payload).toMatchObject({ phone: "+447911123456", contact_method: "phone" });
  });

  it("defaults contact_method to null when no preference is chosen", async () => {
    let payload: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/enquiries", async ({ request }) => {
        payload = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          { id: 4, reference: "E-004", status: "new", ...VALID_GUEST, ...payload },
          { status: 201 },
        );
      }),
    );

    renderWithProviders(<EnquiryFormDialog mode="create" open onOpenChange={() => {}} />);
    await userEvent.type(screen.getByLabelText(/first name/i), "Ada");
    await userEvent.type(screen.getByLabelText(/last name/i), "Lovelace");
    await userEvent.type(screen.getByLabelText(/email/i), "ada@example.com");
    await userEvent.click(screen.getByRole("button", { name: /create/i }));

    await waitFor(() => expect(payload).not.toBeNull());
    expect(payload).toMatchObject({ contact_method: null });
  });

  it("hydrates phone + contact_method from an existing enquiry in edit mode", async () => {
    const enquiry = {
      id: 9,
      reference: "E-009",
      status: "new" as const,
      first_name: "Ada",
      last_name: "Lovelace",
      email: "ada@example.com",
      phone: "+447911123456",
      contact_method: "sms" as const,
      adults: 2,
      children: 0,
      request_type: "quote" as const,
      site_source: "main_website" as const,
      is_flexible: false,
      min_bedrooms: null,
      referral_code: "",
      inbound_message: "",
    };

    renderWithProviders(
      <EnquiryFormDialog mode="edit" enquiry={enquiry} open onOpenChange={() => {}} />,
    );

    expect(screen.getByLabelText(/^phone$/i)).toHaveValue("+447911123456");
    expect(screen.getByRole("combobox", { name: /preferred contact method/i })).toHaveTextContent(
      /sms/i,
    );
  });
});
