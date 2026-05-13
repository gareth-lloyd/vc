import { http, HttpResponse } from "msw";
import { Navigate, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";
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
      http.get("/api/v1/properties/casa-norte/contacts", () =>
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
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
    expect(screen.getByText(/Primary/i)).toBeInTheDocument();
    expect(screen.getByText("owner")).toBeInTheDocument();
    expect(screen.getByText("cleaner")).toBeInTheDocument();
  });

  it("splits active and ended assignments", async () => {
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/casa-norte/contacts", () =>
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
    server.use(
      http.get("/api/v1/properties/casa-norte/contacts", () => HttpResponse.json(drfPage([]))),
    );

    setup();
    expect(await screen.findByText(/No contacts assigned/i)).toBeInTheDocument();
  });

  it("falls back to Contact #id when no name or company is available", async () => {
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/casa-norte/contacts", () =>
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
