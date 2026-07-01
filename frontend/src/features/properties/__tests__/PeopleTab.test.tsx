import { http, HttpResponse } from "msw";
import { Navigate, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";
import { useAuthStore } from "@/features/auth/store";
import { PropertyDetailLayout } from "../PropertyDetailLayout";
import { PeopleTab } from "../tabs/PeopleTab";

const propertyFixture = {
  id: 5,
  name: "Casa Norte",
  display_name: "Casa Norte",
  slug: "casa-norte",
  licence_number: "ETV-1234",
  status: "active",
  channel: "direct",
  category: null,
  group: null,
  region: null,
  feature_ids: [],
  legacy_id: null,
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2026-05-01T00:00:00Z",
};

function installBaseHandlers() {
  server.use(http.get("/api/v1/properties/casa-norte", () => HttpResponse.json(propertyFixture)));
}

function setup() {
  return renderWithProviders(
    <Routes>
      <Route path="/properties/:id" element={<PropertyDetailLayout />}>
        <Route index element={<Navigate to="people" replace />} />
        <Route path="people" element={<PeopleTab />} />
      </Route>
    </Routes>,
    { route: "/properties/casa-norte/people" },
  );
}

describe("PeopleTab", () => {
  it("renders resolved contact names with role and primary badge", async () => {
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/5/contacts", () =>
        HttpResponse.json(
          drfPage([
            {
              id: 1,
              property: 5,
              contact: 101,
              role: "owner",
              start_date: "2024-01-01",
              end_date: null,
              is_primary: true,
            },
            {
              id: 2,
              property: 5,
              contact: 102,
              role: "cleaner",
              start_date: "2024-03-01",
              end_date: null,
              is_primary: false,
            },
          ]),
        ),
      ),
      http.get("/api/v1/contacts/101", () =>
        HttpResponse.json({
          id: 101,
          first_name: "Alice",
          last_name: "Owner",
          emails: [{ id: 11, email: "alice@example.com", is_primary: true }],
          phones: [],
        }),
      ),
      http.get("/api/v1/contacts/102", () =>
        HttpResponse.json({
          id: 102,
          first_name: null,
          last_name: null,
          agency: 102,
          agency_detail: {
            id: 102,
            name: "Sparkle Cleaning Ltd",
            org_type: "agency",
            status: "active",
          },
          emails: [],
          phones: [],
        }),
      ),
    );

    setup();

    expect(await screen.findByText("Alice Owner")).toBeInTheDocument();
    expect(await screen.findByText("Sparkle Cleaning Ltd")).toBeInTheDocument();
    expect(screen.getAllByText("alice@example.com").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Primary/i).length).toBeGreaterThanOrEqual(1);
    // Known roles render their human label; unknown legacy values fall back to
    // the raw (underscore-spaced) string.
    expect(screen.getByText("Owner")).toBeInTheDocument();
    expect(screen.getByText("cleaner")).toBeInTheDocument();
  });

  it("renders an organisation-assignee row by org name without a contact fetch", async () => {
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/5/contacts", () =>
        HttpResponse.json(
          drfPage([
            {
              id: 3,
              property: 5,
              contact: null,
              organisation: 7,
              organisation_detail: { id: 7, name: "Acme Management Co" },
              role: "management_company",
              start_date: "2024-01-01",
              end_date: null,
              is_primary: false,
            },
          ]),
        ),
      ),
      // No /api/v1/contacts/* handler: an org row must NOT fetch a Person.
      // MSW is configured with onUnhandledRequest: "error", so a stray fetch
      // would fail this test.
    );

    setup();

    expect(await screen.findByText("Acme Management Co")).toBeInTheDocument();
    expect(screen.getByText("Organisation")).toBeInTheDocument();
  });

  it("splits active and ended assignments", async () => {
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/5/contacts", () =>
        HttpResponse.json(
          drfPage([
            {
              id: 1,
              property: 5,
              contact: 101,
              role: "owner",
              start_date: "2024-01-01",
              end_date: null,
              is_primary: true,
            },
            {
              id: 2,
              property: 5,
              contact: 102,
              role: "agent",
              start_date: "2023-01-01",
              end_date: "2024-01-01",
              is_primary: false,
            },
          ]),
        ),
      ),
      http.get("/api/v1/contacts/101", () =>
        HttpResponse.json({
          id: 101,
          first_name: "Alice",
          last_name: "Owner",
          emails: [],
          phones: [],
        }),
      ),
      http.get("/api/v1/contacts/102", () =>
        HttpResponse.json({
          id: 102,
          first_name: "Bob",
          last_name: "Agent",
          emails: [],
          phones: [],
        }),
      ),
    );

    setup();

    expect(await screen.findByText(/Active assignments/i)).toBeInTheDocument();
    expect(await screen.findByText(/Ended assignments/i)).toBeInTheDocument();
    expect(await screen.findByText("Alice Owner")).toBeInTheDocument();
    expect(await screen.findByText("Bob Agent")).toBeInTheDocument();
  });

  it("renders empty state when no contacts are assigned", async () => {
    installBaseHandlers();
    server.use(http.get("/api/v1/properties/5/contacts", () => HttpResponse.json(drfPage([]))));

    setup();
    expect(await screen.findByText(/No contacts assigned/i)).toBeInTheDocument();
  });

  it("shows Add contact button when user has RESERVATIONS role", async () => {
    useAuthStore.getState().setMe(
      {
        id: 1,
        email: "a@test.com",
        first_name: "A",
        last_name: "T",
        is_active: true,
        is_staff: true,
        is_superuser: false,
        preferred_language: "en",
        role: "RESERVATIONS",
      },
      { role: "RESERVATIONS", is_superuser: false, permissions: [] },
    );
    installBaseHandlers();
    server.use(http.get("/api/v1/properties/5/contacts", () => HttpResponse.json(drfPage([]))));
    setup();
    expect(await screen.findByRole("button", { name: /add contact/i })).toBeEnabled();
    useAuthStore.getState().clear();
  });

  it("disables Add contact button when user lacks RESERVATIONS role", async () => {
    useAuthStore.getState().setMe(
      {
        id: 1,
        email: "a@test.com",
        first_name: "A",
        last_name: "T",
        is_active: true,
        is_staff: true,
        is_superuser: false,
        preferred_language: "en",
        role: "VIEWER",
      },
      { role: "VIEWER", is_superuser: false, permissions: [] },
    );
    installBaseHandlers();
    server.use(http.get("/api/v1/properties/5/contacts", () => HttpResponse.json(drfPage([]))));
    setup();
    expect(await screen.findByRole("button", { name: /add contact/i })).toBeDisabled();
    useAuthStore.getState().clear();
  });

  it("deletes an assignment after confirmation", async () => {
    useAuthStore.getState().setMe(
      {
        id: 1,
        email: "a@test.com",
        first_name: "A",
        last_name: "T",
        is_active: true,
        is_staff: true,
        is_superuser: false,
        preferred_language: "en",
        role: "RESERVATIONS",
      },
      { role: "RESERVATIONS", is_superuser: false, permissions: [] },
    );
    installBaseHandlers();
    let deleteCalled = false;
    server.use(
      http.get("/api/v1/properties/5/contacts", () =>
        HttpResponse.json(
          drfPage([
            {
              id: 1,
              property: 5,
              contact: 101,
              role: "owner",
              start_date: null,
              end_date: null,
              is_primary: false,
            },
          ]),
        ),
      ),
      http.get("/api/v1/contacts/101", () =>
        HttpResponse.json({
          id: 101,
          first_name: "Alice",
          last_name: "Owner",
          emails: [],
          phones: [],
        }),
      ),
      http.delete("/api/v1/properties/5/contacts/1", () => {
        deleteCalled = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    setup();
    expect(await screen.findByText("Alice Owner")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /actions/i }));
    await userEvent.click(screen.getByText(/remove/i));
    await userEvent.click(await screen.findByRole("button", { name: /remove/i }));
    await waitFor(() => expect(deleteCalled).toBe(true));
    useAuthStore.getState().clear();
  });

  it("auto-selects a contact created inline back into the assignment picker (GAP-027)", async () => {
    useAuthStore.getState().setMe(
      {
        id: 1,
        email: "a@test.com",
        first_name: "A",
        last_name: "T",
        is_active: true,
        is_staff: true,
        is_superuser: false,
        preferred_language: "en",
        role: "RESERVATIONS",
      },
      { role: "RESERVATIONS", is_superuser: false, permissions: [] },
    );
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/5/contacts", () => HttpResponse.json(drfPage([]))),
      http.post("/api/v1/contacts", () =>
        HttpResponse.json(
          {
            id: 500,
            first_name: "Fresh",
            last_name: "Owner",
            agency: null,
            agency_detail: null,
            emails: [],
            phones: [],
          },
          { status: 201 },
        ),
      ),
    );

    setup();

    // Open the assignment dialog, then jump to inline contact creation. Two
    // comboboxes exist — the contact picker (popup=dialog) and the role Select
    // (popup=listbox) — so target the picker by its popup type.
    await userEvent.click(await screen.findByRole("button", { name: /add contact/i }));
    const pickerTrigger = () =>
      screen.getAllByRole("combobox").find((el) => el.getAttribute("aria-haspopup") === "dialog")!;
    await userEvent.click(pickerTrigger());
    await userEvent.click(await screen.findByRole("button", { name: /create new contact/i }));

    // Fill the inline contact form and create. A new active contact needs at
    // least one channel (the create schema's channel_required rule), so supply
    // an email — otherwise the form blocks submit and never hands back.
    await userEvent.type(await screen.findByLabelText(/first name/i), "Fresh");
    await userEvent.type(screen.getByLabelText(/^email$/i), "fresh@example.com");
    await userEvent.click(screen.getByRole("button", { name: /^create contact$/i }));

    // The assignment dialog re-opens with the new contact already selected:
    // the picker trigger now shows its name instead of the placeholder.
    await waitFor(() => expect(pickerTrigger()).toHaveTextContent("Fresh Owner"));

    // Close the dialog and re-open it manually — the picker must start blank,
    // not carry the just-created contact forward into an unrelated assignment.
    await userEvent.click(screen.getByRole("button", { name: /^cancel$/i }));
    await userEvent.click(await screen.findByRole("button", { name: /add contact/i }));
    expect(pickerTrigger()).toHaveTextContent(/select a contact/i);
    useAuthStore.getState().clear();
  });

  it("offers the reconciled ContactRole set in the role dropdown (GAP-048)", async () => {
    useAuthStore.getState().setMe(
      {
        id: 1,
        email: "a@test.com",
        first_name: "A",
        last_name: "T",
        is_active: true,
        is_staff: true,
        is_superuser: false,
        preferred_language: "en",
        role: "RESERVATIONS",
      },
      { role: "RESERVATIONS", is_superuser: false, permissions: [] },
    );
    installBaseHandlers();
    server.use(http.get("/api/v1/properties/5/contacts", () => HttpResponse.json(drfPage([]))));
    setup();

    await userEvent.click(await screen.findByRole("button", { name: /add contact/i }));
    // The role <Select> is the combobox labelled "Role" (the contact picker is a
    // separate combobox with a dialog popup).
    await userEvent.click(screen.getByRole("combobox", { name: /role/i }));

    // L2-1 reconciled the enum: villa_admin + management_company are now offered,
    // and MANAGER reads "Villa Manager" (was "Manager").
    expect(await screen.findByRole("option", { name: "Villa Admin" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Management Company" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Villa Manager" })).toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("falls back to Contact #id when no name or company is available", async () => {
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/5/contacts", () =>
        HttpResponse.json(
          drfPage([
            {
              id: 1,
              property: 5,
              contact: 999,
              role: "owner",
              start_date: null,
              end_date: null,
              is_primary: false,
            },
          ]),
        ),
      ),
      http.get("/api/v1/contacts/999", () =>
        HttpResponse.json({
          id: 999,
          first_name: null,
          last_name: null,
          agency: null,
          agency_detail: null,
          emails: [],
          phones: [],
        }),
      ),
    );

    setup();
    expect(await screen.findByText("Contact #999")).toBeInTheDocument();
  });
});
