import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { queryKeys } from "@/lib/query/keys";
import type { EnquiryDetail } from "@/features/enquiries/schemas";
import { EnquirySummaryHeader } from "../components/EnquirySummaryHeader";

function enquiry(overrides: Partial<EnquiryDetail> = {}): EnquiryDetail {
  return {
    id: 99,
    reference: "ENQ-99",
    status: "new",
    person: null,
    first_name: "Ada",
    last_name: "Lovelace",
    email: "ada@example.com",
    phone: "",
    contact_method: null,
    property: null,
    region: null,
    date_from: "2026-07-04",
    date_to: "2026-07-11",
    adults: 2,
    children: 1,
    request_type: "quote",
    assigned_to: null,
    agent: null,
    site_source: "main_website",
    created_at: null,
    updated_at: null,
    is_flexible: false,
    flexibility_days: 0,
    min_bedrooms: null,
    referral_code: "",
    inbound_message: "",
    lead_status: "warm",
    lost_reason: "",
    quotes_to_convert: null,
    quotations: [],
    ...overrides,
  };
}

const contactFixture = {
  id: 42,
  first_name: "Ada",
  last_name: "Lovelace",
  booking_count: 2,
  is_repeat_customer: true,
  tags: ["vip", "trade"],
  emails: [],
  phones: [],
};

function mockContact(overrides: Record<string, unknown> = {}) {
  server.use(
    http.get("/api/v1/contacts/42", () => HttpResponse.json({ ...contactFixture, ...overrides })),
  );
}

describe("EnquirySummaryHeader", () => {
  it("renders the guest, reference, dates, party, and capture context", () => {
    renderWithProviders(<EnquirySummaryHeader enquiry={enquiry({ min_bedrooms: 3 })} />);

    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("ENQ-99")).toBeInTheDocument();
    expect(
      screen.getByText(/4 Jul 2026 → 11 Jul 2026 · 2 adults · 1 children · min 3 bedrooms/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Quote · Main website/)).toBeInTheDocument();
  });

  it("appends the ± flexibility to the date range when set", () => {
    renderWithProviders(<EnquirySummaryHeader enquiry={enquiry({ flexibility_days: 2 })} />);

    expect(screen.getByText(/4 Jul 2026 → 11 Jul 2026 · ± 2 days/)).toBeInTheDocument();
  });

  it("badges a flexible-dates enquiry", () => {
    renderWithProviders(<EnquirySummaryHeader enquiry={enquiry({ is_flexible: true })} />);

    expect(screen.getByText("Flexible dates")).toBeInTheDocument();
  });

  it("omits dates and the flexible badge when the enquiry has neither", () => {
    renderWithProviders(<EnquirySummaryHeader enquiry={enquiry({ date_from: null })} />);

    expect(screen.queryByText(/Jul 2026/)).not.toBeInTheDocument();
    expect(screen.queryByText("Flexible dates")).not.toBeInTheDocument();
  });

  it("opens the enquiry edit dialog from the Edit button", async () => {
    renderWithProviders(<EnquirySummaryHeader enquiry={enquiry()} />);

    await userEvent.click(screen.getByRole("button", { name: /edit/i }));

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    // Edit mode hydrates the form from the enquiry.
    expect(screen.getByLabelText(/first name/i)).toHaveValue("Ada");
  });

  describe("client tags and Repeat badge (GAP-116)", () => {
    it("shows the linked client's tag chips", async () => {
      mockContact();
      renderWithProviders(<EnquirySummaryHeader enquiry={enquiry({ person: 42 })} />);

      expect(await screen.findByText("VIP")).toBeInTheDocument();
      expect(screen.getByText("Trade")).toBeInTheDocument();
    });

    it("badges a repeat customer", async () => {
      mockContact();
      renderWithProviders(<EnquirySummaryHeader enquiry={enquiry({ person: 42 })} />);

      expect(await screen.findByText("Repeat")).toBeInTheDocument();
      expect(screen.getByText("2 bookings")).toBeInTheDocument();
    });

    it("does not badge a first-time customer", async () => {
      mockContact({ is_repeat_customer: false, booking_count: 0 });
      renderWithProviders(<EnquirySummaryHeader enquiry={enquiry({ person: 42 })} />);

      // The chips prove the contact has loaded before asserting the absence.
      expect(await screen.findByText("VIP")).toBeInTheDocument();
      expect(screen.queryByText("Repeat")).not.toBeInTheDocument();
    });

    it("does not fetch or render anything when no client is linked", async () => {
      let hits = 0;
      server.use(
        http.get("/api/v1/contacts/:id", () => {
          hits += 1;
          return HttpResponse.json(contactFixture);
        }),
      );
      renderWithProviders(<EnquirySummaryHeader enquiry={enquiry({ person: null })} />);

      expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
      await new Promise((resolve) => setTimeout(resolve, 20));
      expect(hits).toBe(0);
      expect(screen.queryByText("Repeat")).not.toBeInTheDocument();
      expect(screen.queryByText(/booking/)).not.toBeInTheDocument();
    });

    it("renders nothing extra for an untagged first-time customer", async () => {
      mockContact({ tags: [], is_repeat_customer: false, booking_count: 0 });
      const { queryClient } = renderWithProviders(
        <EnquirySummaryHeader enquiry={enquiry({ person: 42 })} />,
      );

      await waitFor(() =>
        expect(queryClient.getQueryState(queryKeys.contacts.detail(42))?.status).toBe("success"),
      );
      expect(screen.queryByText("Repeat")).not.toBeInTheDocument();
      expect(screen.queryByText(/booking/)).not.toBeInTheDocument();
      // Title row holds only the guest name and reference — no empty chip wrapper.
      expect(screen.getByText("ENQ-99").parentElement?.children).toHaveLength(2);
    });

    it("keeps the header intact when the contact read fails", async () => {
      server.use(
        http.get("/api/v1/contacts/42", () =>
          HttpResponse.json({ detail: "Not found." }, { status: 404 }),
        ),
      );
      const { queryClient } = renderWithProviders(
        <EnquirySummaryHeader enquiry={enquiry({ person: 42 })} />,
      );

      await waitFor(() =>
        expect(queryClient.getQueryState(queryKeys.contacts.detail(42))?.status).toBe("error"),
      );
      expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
      expect(screen.getByText("ENQ-99")).toBeInTheDocument();
      expect(screen.queryByText("Repeat")).not.toBeInTheDocument();
    });
  });
});
