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
    http.get(`/api/v1/contacts/${id}/past-stays`, () => HttpResponse.json(emptyPage)),
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

  it("renders the migration sentinel as unlinked, not as a customer", async () => {
    // GAP-118: the legacy load parks a quotation whose client it could not
    // resolve on one sentinel Person. It is not a customer, so the rail must
    // not show its name, its tags, or an editor that would write to it.
    server.use(
      http.get("/api/v1/contacts/7", () =>
        HttpResponse.json({
          id: 7,
          first_name: "Unknown",
          last_name: "Client",
          kind: "customer",
          // What the backend actually returns for the sentinel — without it
          // `isClientContact` is false and the tag-editor assertion below
          // passes vacuously, since the editor would not mount either way.
          contact_types: ["customer"],
          tags: ["vip"],
          is_unknown_client: true,
          emails: [],
          phones: [],
        }),
      ),
    );

    renderWithProviders(<CustomerProfilePanel personId={7} />);

    expect(await screen.findByText(/no customer linked/i)).toBeInTheDocument();
    expect(screen.queryByText("Unknown Client")).not.toBeInTheDocument();
    expect(screen.queryByText("VIP")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /tag/i })).not.toBeInTheDocument();
  });

  it("still renders an ordinary customer whose flag is false", async () => {
    server.use(
      http.get("/api/v1/contacts/9", () =>
        HttpResponse.json({ ...contactFixture, is_unknown_client: false }),
      ),
    );
    mockNestedReads(9);

    renderWithProviders(<CustomerProfilePanel personId={9} />);

    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
  });
});
