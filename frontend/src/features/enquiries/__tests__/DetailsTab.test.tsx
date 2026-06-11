import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/render";
import { DetailsTab } from "../tabs/DetailsTab";
import type { EnquiryDetail } from "../schemas";

// A guest-linked enquiry: the denormalised contact fields are blank (the
// lead came in attached to an existing Guest), so the panel must fall back
// to the guest_* fields the API sources from the linked Guest.
const guestLinkedEnquiry: EnquiryDetail = {
  id: 7,
  reference: "E-XYZ-007",
  status: "new",
  guest: 42,
  guest_name: "Ada Lovelace",
  guest_email: "ada@example.com",
  guest_phone: "+44 7700 900123",
  guest_contact_method: "sms",
  first_name: "",
  last_name: "",
  email: "",
  phone: "",
  contact_method: null,
  property: null,
  region: null,
  date_from: "2026-07-01",
  date_to: "2026-07-08",
  adults: 2,
  children: 0,
  request_type: "quote",
  assigned_to: null,
  agent: null,
  site_source: "main_website",
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-02T00:00:00Z",
  is_flexible: false,
  flexibility_days: 0,
  min_bedrooms: null,
  referral_code: "",
  inbound_message: "",
  quotations: [],
};

describe("DetailsTab guest panel", () => {
  it("falls back to linked-guest fields when denormalised fields are blank", () => {
    renderWithProviders(<DetailsTab enquiry={guestLinkedEnquiry} />);
    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("ada@example.com")).toBeInTheDocument();
    expect(screen.getByText("+44 7700 900123")).toBeInTheDocument();
    expect(screen.getByText("SMS")).toBeInTheDocument();
  });

  it("prefers the denormalised contact fields when present", () => {
    renderWithProviders(
      <DetailsTab
        enquiry={{
          ...guestLinkedEnquiry,
          email: "grace@example.com",
          phone: "+44 7700 900999",
          contact_method: "email",
        }}
      />,
    );
    expect(screen.getByText("grace@example.com")).toBeInTheDocument();
    expect(screen.getByText("+44 7700 900999")).toBeInTheDocument();
    expect(screen.getByText("Preferred contact").nextElementSibling).toHaveTextContent("Email");
  });
});
