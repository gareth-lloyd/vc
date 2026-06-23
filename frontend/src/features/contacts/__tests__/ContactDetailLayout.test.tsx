import { http, HttpResponse } from "msw";
import { Navigate, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { ContactDetailLayout } from "../ContactDetailLayout";
import { DetailsTab } from "../tabs/DetailsTab";
import { ComingSoonTab } from "@/components/feedback/ComingSoonTab";

const contactFixture = {
  id: 7,
  title: "Dr",
  first_name: "Ada",
  last_name: "Lovelace",
  agency: 100,
  agency_detail: { id: 100, name: "Analytical Engines", org_type: "agency", status: "active" },
  website_url: "https://example.com",
  preferred_method: "email",
  address_line_1: "1 Babbage Way",
  address_line_2: null,
  notes: "Wants the suite with the sea view.",
  status: "active",
  emails: [{ id: 11, email: "ada@example.com", label: "work", is_primary: true }],
  phones: [{ id: 21, number: "+44 7000 000 000", label: "mobile", is_primary: true }],
};

function setup(initial: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/contacts/:id" element={<ContactDetailLayout />}>
        <Route index element={<Navigate to="details" replace />} />
        <Route path="details" element={<DetailsTab />} />
        <Route path="notes" element={<ComingSoonTab tabName="Notes" />} />
      </Route>
    </Routes>,
    { route: initial },
  );
}

describe("ContactDetailLayout", () => {
  it("renders the contact name and details tab", async () => {
    server.use(http.get("/api/v1/contacts/7", () => HttpResponse.json(contactFixture)));
    setup("/contacts/7/details");
    await waitFor(() => expect(screen.getAllByText("Ada Lovelace")[0]).toBeInTheDocument());
    expect(await screen.findByText("ada@example.com")).toBeInTheDocument();
    expect(screen.getByText("+44 7000 000 000")).toBeInTheDocument();
  });

  it("navigates between tabs", async () => {
    server.use(http.get("/api/v1/contacts/7", () => HttpResponse.json(contactFixture)));
    setup("/contacts/7/details");
    await screen.findByText("ada@example.com");
    await userEvent.click(screen.getByRole("link", { name: "Notes" }));
    expect(await screen.findByText(/Notes — coming in next phase/i)).toBeInTheDocument();
  });
});

describe("ContactDetailLayout customer-360 profile (GAP-042)", () => {
  it("shows the Repeat badge and booking count for a returning customer", async () => {
    server.use(
      http.get("/api/v1/contacts/7", () =>
        HttpResponse.json({ ...contactFixture, booking_count: 3, is_repeat_customer: true }),
      ),
    );
    setup("/contacts/7/details");
    await waitFor(() => expect(screen.getAllByText("Ada Lovelace")[0]).toBeInTheDocument());
    expect(screen.getByText("Repeat")).toBeInTheDocument();
    expect(screen.getByText("3 bookings")).toBeInTheDocument();
  });

  it("omits the Repeat badge for a first-time contact", async () => {
    server.use(
      http.get("/api/v1/contacts/7", () =>
        HttpResponse.json({ ...contactFixture, booking_count: 0, is_repeat_customer: false }),
      ),
    );
    setup("/contacts/7/details");
    await screen.findByText("ada@example.com");
    expect(screen.queryByText("Repeat")).not.toBeInTheDocument();
  });

  it("hides the address behind a collapsible section", async () => {
    server.use(
      http.get("/api/v1/contacts/7", () =>
        HttpResponse.json({
          ...contactFixture,
          town: "Athens",
          post_code: "10557",
          country_name: "Greece",
        }),
      ),
    );
    setup("/contacts/7/details");
    await screen.findByText("ada@example.com");
    // Collapsed by default — the town is not rendered until expanded.
    expect(screen.queryByText("Athens")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Address" }));
    expect(await screen.findByText("Athens")).toBeInTheDocument();
    expect(screen.getByText("Greece")).toBeInTheDocument();
  });
});

describe("ContactDetailLayout error differentiation", () => {
  it("shows 'Contact not found' on 404 without a retry button", async () => {
    server.use(
      http.get("/api/v1/contacts/999", () =>
        HttpResponse.json({ detail: "Not found." }, { status: 404 }),
      ),
    );
    renderWithProviders(
      <Routes>
        <Route path="/contacts/:id" element={<ContactDetailLayout />}>
          <Route index element={<Navigate to="details" replace />} />
          <Route path="details" element={<DetailsTab />} />
        </Route>
      </Routes>,
      { route: "/contacts/999/details" },
    );
    expect(await screen.findByText("Contact not found")).toBeInTheDocument();
    expect(screen.getByText(/may have been deleted/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
  });

  it("shows 'Couldn't load this contact' on 500 with a retry button", async () => {
    server.use(
      http.get("/api/v1/contacts/8", () =>
        HttpResponse.json({ detail: "Server error" }, { status: 500 }),
      ),
    );
    renderWithProviders(
      <Routes>
        <Route path="/contacts/:id" element={<ContactDetailLayout />}>
          <Route index element={<Navigate to="details" replace />} />
          <Route path="details" element={<DetailsTab />} />
        </Route>
      </Routes>,
      { route: "/contacts/8/details" },
    );
    expect(await screen.findByText("Couldn't load this contact")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });
});
