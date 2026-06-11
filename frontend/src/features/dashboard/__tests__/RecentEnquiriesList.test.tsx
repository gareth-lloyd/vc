import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";
import { RecentEnquiriesList } from "../components/RecentEnquiriesList";

const guestLinkedRow = {
  id: 7,
  reference: "E-XYZ-007",
  status: "new",
  guest: 42,
  guest_name: "Ada Lovelace",
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
};

describe("RecentEnquiriesList", () => {
  it("shows the guest name for guest-linked rows, never a doubled reference", async () => {
    server.use(http.get("/api/v1/enquiries", () => HttpResponse.json(drfPage([guestLinkedRow]))));
    renderWithProviders(<RecentEnquiriesList />);
    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
    // The reference renders once (right-hand column), not as the name too.
    expect(screen.getAllByText("E-XYZ-007")).toHaveLength(1);
  });

  it("falls back to an em-dash when no name or email exists", async () => {
    const anonymous = { ...guestLinkedRow, guest: null, guest_name: null };
    server.use(http.get("/api/v1/enquiries", () => HttpResponse.json(drfPage([anonymous]))));
    renderWithProviders(<RecentEnquiriesList />);
    expect(await screen.findByText("—")).toBeInTheDocument();
    expect(screen.getAllByText("E-XYZ-007")).toHaveLength(1);
  });
});
