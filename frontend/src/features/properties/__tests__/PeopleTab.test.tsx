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
          company: "Sparkle Cleaning Ltd",
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
    expect(screen.getByText("owner")).toBeInTheDocument();
    expect(screen.getByText("cleaner")).toBeInTheDocument();
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
          company: null,
          emails: [],
          phones: [],
        }),
      ),
    );

    setup();
    expect(await screen.findByText("Contact #999")).toBeInTheDocument();
  });
});
