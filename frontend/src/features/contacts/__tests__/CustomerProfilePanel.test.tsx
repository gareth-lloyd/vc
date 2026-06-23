import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { CustomerProfilePanel } from "../components/CustomerProfilePanel";

const contactFixture = {
  id: 9,
  first_name: "Ada",
  last_name: "Lovelace",
  agency_detail: { id: 1, name: "Analytical Engines", org_type: "agency", status: "active" },
  booking_count: 2,
  is_repeat_customer: true,
  tags: ["vip"],
  emails: [],
  phones: [],
};

const emptyPage = { count: 0, next: null, previous: null, results: [] };

function mockNestedReads(id: number) {
  server.use(
    http.get(`/api/v1/contacts/${id}/relationships`, () => HttpResponse.json(emptyPage)),
    http.get(`/api/v1/contacts/${id}/enquiries`, () => HttpResponse.json(emptyPage)),
    http.get(`/api/v1/contacts/${id}/bookings`, () => HttpResponse.json(emptyPage)),
  );
}

describe("CustomerProfilePanel", () => {
  it("renders the identity, repeat badge, and history accordions for a person", async () => {
    server.use(http.get("/api/v1/contacts/9", () => HttpResponse.json(contactFixture)));
    mockNestedReads(9);

    renderWithProviders(<CustomerProfilePanel personId={9} />);

    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("Analytical Engines")).toBeInTheDocument();
    expect(screen.getByText("Repeat")).toBeInTheDocument();
    // The booking-history accordion is part of the panel.
    await waitFor(() => expect(screen.getByText(/previous bookings/i)).toBeInTheDocument());
  });

  it("shows an empty hint when no customer is linked", () => {
    renderWithProviders(<CustomerProfilePanel personId={null} />);
    expect(screen.getByText(/no customer linked/i)).toBeInTheDocument();
  });
});
