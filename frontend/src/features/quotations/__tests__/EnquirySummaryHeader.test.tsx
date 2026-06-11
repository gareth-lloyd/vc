import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/render";
import type { EnquiryDetail } from "@/features/enquiries/schemas";
import { EnquirySummaryHeader } from "../components/EnquirySummaryHeader";

function enquiry(overrides: Partial<EnquiryDetail> = {}): EnquiryDetail {
  return {
    id: 99,
    reference: "ENQ-99",
    status: "new",
    guest: null,
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
    quotations: [],
    ...overrides,
  };
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
});
