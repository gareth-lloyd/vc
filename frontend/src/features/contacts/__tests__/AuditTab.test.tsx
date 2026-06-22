import { http, HttpResponse } from "msw";
import { Navigate, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { ContactDetailLayout } from "../ContactDetailLayout";
import { AuditTab } from "../tabs/AuditTab";

const CONTACT_ID = 7;

const contactFixture = {
  id: CONTACT_ID,
  title: "Dr",
  first_name: "Ada",
  last_name: "Lovelace",
  agency: 100,
  agency_detail: { id: 100, name: "Analytical Engines", org_type: "agency", status: "active" },
  website_url: "https://example.com",
  preferred_method: "email",
  address_line_1: "1 Babbage Way",
  address_line_2: null,
  notes: "",
  status: "active",
  emails: [{ id: 11, email: "ada@example.com", label: "work", is_primary: true }],
  phones: [],
};

interface AuditEntryFixture {
  id: string;
  entity_type: string;
  object_id: string;
  actor: number | null;
  actor_email: string | null;
  field_diffs: Record<string, unknown>;
  correlation_id: string | null;
  created_at: string;
}

function entry(overrides: Partial<AuditEntryFixture> = {}): AuditEntryFixture {
  return {
    id: "00000000-0000-0000-0000-000000000001",
    entity_type: "accounts.person",
    object_id: String(CONTACT_ID),
    actor: 1,
    actor_email: "ops@example.com",
    field_diffs: { first_name: ["A", "B"] },
    correlation_id: null,
    created_at: "2026-05-10T10:00:00Z",
    ...overrides,
  };
}

function listResponse(entries: AuditEntryFixture[], opts: { next?: string | null } = {}) {
  return {
    count: entries.length,
    next: opts.next ?? null,
    previous: null,
    results: entries,
  };
}

function setup(route = `/contacts/${CONTACT_ID}/audit`) {
  return renderWithProviders(
    <Routes>
      <Route path="/contacts/:id" element={<ContactDetailLayout />}>
        <Route index element={<Navigate to="audit" replace />} />
        <Route path="audit" element={<AuditTab />} />
      </Route>
    </Routes>,
    { route },
  );
}

afterEach(() => {
  server.resetHandlers();
});

describe("contacts AuditTab", () => {
  it("queries the unified Person content type and renders a formatted diff row", async () => {
    let capturedUrl: URL | null = null;
    server.use(
      http.get(`/api/v1/contacts/${CONTACT_ID}`, () => HttpResponse.json(contactFixture)),
      http.get("/api/v1/audit-log", ({ request }) => {
        capturedUrl = new URL(request.url);
        return HttpResponse.json(listResponse([entry()]));
      }),
    );
    setup();

    await waitFor(() => expect(screen.getByText("Updated")).toBeInTheDocument());
    // The bug being fixed: GAP-045 renamed the model, so the entity_type must be
    // `accounts.person`, not the now-nonexistent `accounts.contact`.
    expect(capturedUrl!.searchParams.get("entity_type")).toBe("accounts.person");
    expect(capturedUrl!.searchParams.get("entity_id")).toBe(String(CONTACT_ID));

    // Formatted `field: old → new` row, not a raw JSON dump.
    expect(screen.getByText("First name")).toBeInTheDocument();
    expect(screen.getByText("A")).toBeInTheDocument();
    expect(screen.getByText("B")).toBeInTheDocument();
    expect(screen.getByText(/ops@example\.com/)).toBeInTheDocument();
  });

  it("renders an empty state when there are no entries", async () => {
    server.use(
      http.get(`/api/v1/contacts/${CONTACT_ID}`, () => HttpResponse.json(contactFixture)),
      http.get("/api/v1/audit-log", () => HttpResponse.json(listResponse([]))),
    );
    setup();
    expect(await screen.findByText(/no history yet/i)).toBeInTheDocument();
  });

  it("renders a permission notice on 403", async () => {
    server.use(
      http.get(`/api/v1/contacts/${CONTACT_ID}`, () => HttpResponse.json(contactFixture)),
      http.get("/api/v1/audit-log", () =>
        HttpResponse.json({ detail: "Forbidden" }, { status: 403 }),
      ),
    );
    setup();
    expect(await screen.findByText(/history requires admin access/i)).toBeInTheDocument();
  });

  it("shows pagination controls when next is present", async () => {
    server.use(
      http.get(`/api/v1/contacts/${CONTACT_ID}`, () => HttpResponse.json(contactFixture)),
      http.get("/api/v1/audit-log", () =>
        HttpResponse.json(listResponse([entry()], { next: "/api/v1/audit-log?page=2" })),
      ),
    );
    setup();
    await waitFor(() => expect(screen.getByText("Updated")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /next/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /previous/i })).toBeDisabled();
  });

  it("renders a deletion banner for a delete row", async () => {
    server.use(
      http.get(`/api/v1/contacts/${CONTACT_ID}`, () => HttpResponse.json(contactFixture)),
      http.get("/api/v1/audit-log", () =>
        HttpResponse.json(
          listResponse([
            entry({ id: "d", field_diffs: { __deleted__: true, last_name: ["Lovelace", null] } }),
          ]),
        ),
      ),
    );
    setup();
    expect(await screen.findByText("Deleted")).toBeInTheDocument();
    expect(screen.getByText(/this record was deleted/i)).toBeInTheDocument();
  });
});
