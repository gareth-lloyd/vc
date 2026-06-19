import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useLocation } from "react-router-dom";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";
import { EnquiryFormDialog } from "../components/EnquiryFormDialog";

const EXISTING_GUEST = {
  id: 55,
  first_name: "Ada",
  last_name: "Lovelace",
  email: "ada@guest.example.com",
  phone: "+447900000000",
  contact_method: "email",
  status: "active",
};

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
            flexibility_days: 0,
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
    expect(payload).toMatchObject({
      date_from: "2026-06-10",
      date_to: "2026-06-17",
      flexibility_days: 0,
    });
  });

  it("navigates to the new enquiry's detail page after creating it", async () => {
    server.use(
      http.post("/api/v1/enquiries", async ({ request }) => {
        const payload = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          { id: 42, reference: "E-042", status: "new", ...VALID_GUEST, ...payload },
          { status: 201 },
        );
      }),
    );

    const LocationProbe = () => {
      const location = useLocation();
      return <div data-testid="location">{location.pathname}</div>;
    };

    renderWithProviders(
      <>
        <EnquiryFormDialog mode="create" open onOpenChange={() => {}} />
        <LocationProbe />
      </>,
    );

    await userEvent.type(screen.getByLabelText(/first name/i), "Ada");
    await userEvent.type(screen.getByLabelText(/last name/i), "Lovelace");
    await userEvent.type(screen.getByLabelText(/email/i), "ada@example.com");
    await userEvent.click(screen.getByRole("button", { name: /create/i }));

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/enquiries/42"));
  });

  it("submits null for unset dates rather than an empty string", async () => {
    let payload: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/enquiries", async ({ request }) => {
        payload = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          { id: 5, reference: "E-005", status: "new", ...VALID_GUEST, ...payload },
          { status: 201 },
        );
      }),
    );

    renderWithProviders(<EnquiryFormDialog mode="create" open onOpenChange={() => {}} />);

    await userEvent.type(screen.getByLabelText(/first name/i), "Ada");
    await userEvent.type(screen.getByLabelText(/last name/i), "Lovelace");
    await userEvent.type(screen.getByLabelText(/email/i), "ada@example.com");
    // Leave both dates untouched — an unset <input type="date"> reads "".
    await userEvent.click(screen.getByRole("button", { name: /create/i }));

    await waitFor(() => expect(payload).not.toBeNull());
    // "" would make DRF's DateField 400 with a "wrong format" error; null is
    // the correct "no date supplied" representation.
    expect(payload).toMatchObject({ date_from: null, date_to: null });
  });

  it("blocks submit and shows an inline error when the end date precedes the start", async () => {
    let posted = false;
    server.use(
      http.post("/api/v1/enquiries", () => {
        posted = true;
        return HttpResponse.json({ id: 6, reference: "E-006", status: "new" }, { status: 201 });
      }),
    );

    renderWithProviders(<EnquiryFormDialog mode="create" open onOpenChange={() => {}} />);

    await userEvent.type(screen.getByLabelText(/first name/i), "Ada");
    await userEvent.type(screen.getByLabelText(/last name/i), "Lovelace");
    await userEvent.type(screen.getByLabelText(/email/i), "ada@example.com");
    await userEvent.clear(screen.getByLabelText(/^from$/i));
    await userEvent.type(screen.getByLabelText(/^from$/i), "2026-07-10");
    await userEvent.clear(screen.getByLabelText(/^to$/i));
    await userEvent.type(screen.getByLabelText(/^to$/i), "2026-07-05");

    await userEvent.click(screen.getByRole("button", { name: /create/i }));

    // Client-side guard renders inline and never hits the network.
    expect(await screen.findByText(/end date can't be before the start date/i)).toBeInTheDocument();
    expect(posted).toBe(false);
  });

  it("submits unshifted dates plus flexibility_days — never widened dates", async () => {
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
            flexibility_days: payload.flexibility_days,
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

    // Click the "+" stepper twice for ±2 days of flexibility.
    const increment = screen.getByRole("button", { name: /increase date spread/i });
    await userEvent.click(increment);
    await userEvent.click(increment);

    // Preview shows the widened SEARCH window, but the stored dates stay true.
    expect(screen.getByText(/2026-06-08/)).toBeInTheDocument();
    expect(screen.getByText(/2026-06-19/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /create/i }));

    await waitFor(() => expect(payload).not.toBeNull());
    expect(payload).toMatchObject({
      date_from: "2026-06-10",
      date_to: "2026-06-17",
      flexibility_days: 2,
    });
  });

  it("seeds the stepper from the enquiry's flexibility_days in edit mode", async () => {
    let payload: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/enquiries/31", async ({ request }) => {
        payload = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          id: 31,
          reference: "E-031",
          status: "new",
          ...VALID_GUEST,
          ...payload,
          referral_code: "",
          quotations: [],
        });
      }),
    );

    const enquiry = {
      id: 31,
      reference: "E-031",
      status: "new" as const,
      first_name: "Ada",
      last_name: "Lovelace",
      email: "ada@example.com",
      phone: "",
      contact_method: null,
      date_from: "2026-06-10",
      date_to: "2026-06-17",
      adults: 2,
      children: 0,
      request_type: "quote" as const,
      site_source: "main_website" as const,
      is_flexible: false,
      flexibility_days: 3,
      min_bedrooms: null,
      referral_code: "",
      inbound_message: "",
      lead_status: "warm" as const,
      lost_reason: "" as const,
      quotes_to_convert: null,
      quotations: [],
    };

    renderWithProviders(
      <EnquiryFormDialog mode="edit" enquiry={enquiry} open onOpenChange={() => {}} />,
    );

    // Stepper hydrated to ±3 — increment is pegged at the cap.
    expect(screen.getByText(/±\s*3\s*days/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /increase date spread/i })).toBeDisabled();

    // Saving without touching it round-trips the stored value.
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(payload).not.toBeNull());
    expect(payload).toMatchObject({
      date_from: "2026-06-10",
      date_to: "2026-06-17",
      flexibility_days: 3,
    });
  });

  it("shows preview_zero text when both dates are set and spread is 0", async () => {
    renderWithProviders(<EnquiryFormDialog mode="create" open onOpenChange={() => {}} />);

    await userEvent.clear(screen.getByLabelText(/^from$/i));
    await userEvent.type(screen.getByLabelText(/^from$/i), "2026-06-10");
    await userEvent.clear(screen.getByLabelText(/^to$/i));
    await userEvent.type(screen.getByLabelText(/^to$/i), "2026-06-17");

    // Spread stays at 0 by default — the more-informative preview_zero copy
    // should appear instead of the generic flexibility hint.
    expect(screen.getByText(/search will use the requested dates/i)).toBeInTheDocument();
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
      flexibility_days: 0,
      min_bedrooms: null,
      referral_code: "",
      inbound_message: "",
      lead_status: "warm" as const,
      lost_reason: "" as const,
      quotes_to_convert: null,
      quotations: [],
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

describe("EnquiryFormDialog server-side field errors", () => {
  const ENQUIRY = {
    id: 21,
    reference: "E-021",
    status: "new" as const,
    first_name: "Ada",
    last_name: "Lovelace",
    email: "ada@example.com",
    phone: "",
    contact_method: null,
    date_from: "2026-07-10",
    date_to: "2026-07-17",
    adults: 2,
    children: 0,
    request_type: "quote" as const,
    site_source: "main_website" as const,
    is_flexible: false,
    flexibility_days: 0,
    min_bedrooms: null,
    referral_code: "",
    inbound_message: "",
    lead_status: "warm" as const,
    lost_reason: "" as const,
    quotes_to_convert: null,
    quotations: [],
  };

  it("renders a 400 field error on date_to inline beside the date field", async () => {
    server.use(
      http.patch("/api/v1/enquiries/21", () =>
        HttpResponse.json(
          { field_errors: { date_to: ["That property is already held for these dates"] } },
          { status: 400 },
        ),
      ),
    );

    renderWithProviders(
      <EnquiryFormDialog mode="edit" enquiry={ENQUIRY} open onOpenChange={() => {}} />,
    );

    // A well-ordered range that passes the client guard but the server rejects
    // for its own reason — the field error must surface, not vanish silently.
    await userEvent.clear(screen.getByLabelText(/^to$/i));
    await userEvent.type(screen.getByLabelText(/^to$/i), "2026-07-20");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    expect(
      await screen.findByText("That property is already held for these dates"),
    ).toBeInTheDocument();
  });

  it("renders a 400 field error on phone inline beside the phone field", async () => {
    server.use(
      http.patch("/api/v1/enquiries/21", () =>
        HttpResponse.json(
          { field_errors: { phone: ["Enter a valid phone number"] } },
          { status: 400 },
        ),
      ),
    );

    renderWithProviders(
      <EnquiryFormDialog mode="edit" enquiry={ENQUIRY} open onOpenChange={() => {}} />,
    );

    await userEvent.type(screen.getByLabelText(/^phone$/i), "12");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    expect(await screen.findByText("Enter a valid phone number")).toBeInTheDocument();
  });
});

describe("EnquiryFormDialog guest resolve-or-create", () => {
  it("links an existing guest, prefills the fields, and submits the guest id", async () => {
    let payload: Record<string, unknown> | null = null;
    server.use(
      http.get("/api/v1/guests", () => HttpResponse.json(drfPage([EXISTING_GUEST]))),
      http.get("/api/v1/guests/55/enquiries", () => HttpResponse.json(drfPage([]))),
      http.post("/api/v1/enquiries", async ({ request }) => {
        payload = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          { id: 7, reference: "E-007", status: "new", ...VALID_GUEST, ...payload },
          { status: 201 },
        );
      }),
    );

    renderWithProviders(<EnquiryFormDialog mode="create" open onOpenChange={() => {}} />);

    // The picker trigger has role=combobox, whose accessible name is not
    // derived from its text content — so target it by its visible label.
    await userEvent.click(
      await screen.findByText(/link an existing guest/i, { selector: "button" }),
    );
    await userEvent.type(screen.getByLabelText(/search guests/i), "ada");
    await userEvent.click(await screen.findByText("Ada Lovelace"));

    // Picking prefills the denorm capture fields.
    expect(screen.getByLabelText(/first name/i)).toHaveValue("Ada");
    expect(screen.getByLabelText(/email/i)).toHaveValue("ada@guest.example.com");

    await userEvent.click(screen.getByRole("button", { name: /create/i }));

    await waitFor(() => expect(payload).not.toBeNull());
    expect(payload).toMatchObject({ guest: 55, email: "ada@guest.example.com" });
  });

  it("unlinking a picked guest submits guest as null (create-new path)", async () => {
    let payload: Record<string, unknown> | null = null;
    server.use(
      http.get("/api/v1/guests", () => HttpResponse.json(drfPage([EXISTING_GUEST]))),
      http.get("/api/v1/guests/55/enquiries", () => HttpResponse.json(drfPage([]))),
      http.post("/api/v1/enquiries", async ({ request }) => {
        payload = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          { id: 8, reference: "E-008", status: "new", ...VALID_GUEST, ...payload },
          { status: 201 },
        );
      }),
    );

    renderWithProviders(<EnquiryFormDialog mode="create" open onOpenChange={() => {}} />);

    await userEvent.click(
      await screen.findByText(/link an existing guest/i, { selector: "button" }),
    );
    await userEvent.type(screen.getByLabelText(/search guests/i), "ada");
    await userEvent.click(await screen.findByText("Ada Lovelace"));

    await userEvent.click(screen.getByRole("button", { name: /unlink/i }));
    // Re-fill the required fields (still editable) and submit.
    await userEvent.type(screen.getByLabelText(/last name/i), "Byron");
    await userEvent.click(screen.getByRole("button", { name: /create/i }));

    await waitFor(() => expect(payload).not.toBeNull());
    expect(payload).toMatchObject({ guest: null });
  });

  it("hydrates the picker from an already-linked guest in edit mode", async () => {
    server.use(
      http.get("/api/v1/guests/55", () => HttpResponse.json(EXISTING_GUEST)),
      http.get("/api/v1/guests/55/enquiries", () => HttpResponse.json(drfPage([]))),
    );

    const enquiry = {
      id: 12,
      reference: "E-012",
      status: "new" as const,
      guest: 55,
      first_name: "Ada",
      last_name: "Lovelace",
      email: "ada@guest.example.com",
      phone: "+447900000000",
      contact_method: "email" as const,
      adults: 2,
      children: 0,
      request_type: "quote" as const,
      site_source: "main_website" as const,
      is_flexible: false,
      flexibility_days: 0,
      min_bedrooms: null,
      referral_code: "",
      inbound_message: "",
      lead_status: "warm" as const,
      lost_reason: "" as const,
      quotes_to_convert: null,
      quotations: [],
    };

    renderWithProviders(
      <EnquiryFormDialog mode="edit" enquiry={enquiry} open onOpenChange={() => {}} />,
    );

    // After hydration the picker trigger shows the linked guest's name (the
    // only place "Ada Lovelace" appears as a single text node — the denorm
    // first/last names are separate input values, not text).
    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
  });

  it("keeps a guest unlinked in edit mode (hydration does not revert the clear)", async () => {
    server.use(
      http.get("/api/v1/guests/55", () => HttpResponse.json(EXISTING_GUEST)),
      http.get("/api/v1/guests/55/enquiries", () => HttpResponse.json(drfPage([]))),
    );

    const enquiry = {
      id: 13,
      reference: "E-013",
      status: "new" as const,
      guest: 55,
      first_name: "Ada",
      last_name: "Lovelace",
      email: "ada@guest.example.com",
      phone: "+447900000000",
      contact_method: "email" as const,
      adults: 2,
      children: 0,
      request_type: "quote" as const,
      site_source: "main_website" as const,
      is_flexible: false,
      flexibility_days: 0,
      min_bedrooms: null,
      referral_code: "",
      inbound_message: "",
      lead_status: "warm" as const,
      lost_reason: "" as const,
      quotes_to_convert: null,
      quotations: [],
    };

    renderWithProviders(
      <EnquiryFormDialog mode="edit" enquiry={enquiry} open onOpenChange={() => {}} />,
    );

    // Wait for hydration, then unlink.
    await screen.findByText("Ada Lovelace");
    await userEvent.click(screen.getByRole("button", { name: /unlink/i }));

    // The clear must stick — the hydration effect must NOT re-link the guest.
    await waitFor(() =>
      expect(
        screen.getByText(/link an existing guest/i, { selector: "button" }),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByText("Ada Lovelace")).not.toBeInTheDocument();
    // The unlink affordance is gone once nothing is linked.
    expect(screen.queryByRole("button", { name: /unlink/i })).not.toBeInTheDocument();
  });
});
