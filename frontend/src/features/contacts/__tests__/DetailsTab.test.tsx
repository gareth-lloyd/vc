import { http, HttpResponse } from "msw";
import { Outlet, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { DetailsTab } from "../tabs/DetailsTab";
import type { Contact } from "../schemas";

const emptyPage = { count: 0, next: null, previous: null, results: [] };

const STAYS = {
  count: 1,
  next: null,
  previous: null,
  results: [
    {
      id: 1,
      booking_number: "BN123",
      villa_name: "Kerasia Olive Press",
      property: 10,
      property_name: "Kerasia Olive Press",
      destination: "Corfu",
      year: 2025,
      notes: "",
      date_from: "2025-09-15",
      date_to: "2025-09-22",
      amount: "4740.00",
      currency_code: "EUR",
    },
  ],
};

function renderTab(contact: Partial<Contact> = {}) {
  const full = {
    id: 7,
    first_name: "Kate",
    last_name: "Ferguson",
    contact_types: ["customer"],
    emails: [],
    phones: [],
    ...contact,
  } as unknown as Contact;
  return renderWithProviders(
    <Routes>
      <Route path="/contacts/:id" element={<Outlet context={{ contact: full }} />}>
        <Route path="details" element={<DetailsTab />} />
      </Route>
    </Routes>,
    { route: "/contacts/7/details" },
  );
}

function mockNestedReads(id: number, stays: typeof emptyPage | typeof STAYS = emptyPage) {
  server.use(
    http.get(`/api/v1/contacts/${id}/relationships`, () => HttpResponse.json(emptyPage)),
    http.get(`/api/v1/contacts/${id}/enquiries`, () => HttpResponse.json(emptyPage)),
    http.get(`/api/v1/contacts/${id}/bookings`, () => HttpResponse.json(emptyPage)),
    http.get(`/api/v1/contacts/${id}/past-stays`, () => HttpResponse.json(stays)),
  );
}

describe("DetailsTab history sections", () => {
  // GAP-089 landed PastStay for the Customer-360 "past stays" view, but wired
  // the accordion into CustomerProfilePanel only — so a client's own detail
  // page showed enquiries and (always-empty, GAP-089) bookings and silently
  // dropped the stay history that is the whole historic record for a
  // pre-cutover customer.
  it("shows the past-stay history alongside enquiries and bookings", async () => {
    mockNestedReads(7, STAYS);

    renderTab();

    expect(await screen.findByText(/imported bookings \(1\)/i)).toBeInTheDocument();
    expect(screen.getByText(/previous bookings/i)).toBeInTheDocument();
  });

  // A customer with no stays still gets the section (uncounted, like the
  // enquiry and booking accordions beside it) rather than a hole in the page.
  it("still renders the past-stay section when the customer has none", async () => {
    mockNestedReads(7);

    renderTab();

    expect(await screen.findByText(/^imported bookings$/i)).toBeInTheDocument();
  });
});

describe("DetailsTab tags section", () => {
  it("gives a client an editable tag section", async () => {
    mockNestedReads(7);
    renderTab({ tags: ["vip"] });

    expect(await screen.findByRole("button", { name: /edit tags/i })).toBeInTheDocument();
  });

  it("keeps the unknown-client sentinel's tags read-only", async () => {
    // GAP-118: the sentinel is reachable from the Clients directory, where this
    // is the app's most writable surface onto it. Its tags stay visible (the
    // data is real) but the editor that would PATCH the placeholder does not.
    mockNestedReads(7);
    renderTab({ tags: ["vip"], is_unknown_client: true });

    expect(await screen.findByText("VIP")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /edit tags/i })).not.toBeInTheDocument();
  });
});
