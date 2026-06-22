import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { AuditHistory } from "../AuditHistory";

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

function entry(
  field_diffs: Record<string, unknown>,
  overrides: Partial<AuditEntryFixture> = {},
): AuditEntryFixture {
  return {
    id: "00000000-0000-0000-0000-000000000001",
    entity_type: "properties.propertyfinance",
    object_id: "5",
    actor: 1,
    actor_email: "ops@example.com",
    field_diffs,
    correlation_id: null,
    created_at: "2026-05-10T10:00:00Z",
    ...overrides,
  };
}

function listResponse(entries: AuditEntryFixture[], opts: { next?: string | null } = {}) {
  return { count: entries.length, next: opts.next ?? null, previous: null, results: entries };
}

afterEach(() => {
  server.resetHandlers();
});

describe("AuditHistory", () => {
  it("renders a commission edit as old → new with the actor (GAP-021 acceptance)", async () => {
    server.use(
      http.get("/api/v1/audit-log", () =>
        HttpResponse.json(listResponse([entry({ commission_amount: ["10.00", "12.50"] })])),
      ),
    );
    renderWithProviders(<AuditHistory entityType="properties.propertyfinance" entityId={5} />);

    await waitFor(() => expect(screen.getByText("Commission amount")).toBeInTheDocument());
    expect(screen.getByText("10.00")).toBeInTheDocument();
    expect(screen.getByText("12.50")).toBeInTheDocument();
    expect(screen.getByText(/ops@example\.com/)).toBeInTheDocument();
    expect(screen.getByText("Updated")).toBeInTheDocument();
  });

  it("passes the date filters to the API, widening the upper bound to end-of-day", async () => {
    const urls: string[] = [];
    server.use(
      http.get("/api/v1/audit-log", ({ request }) => {
        urls.push(request.url);
        return HttpResponse.json(listResponse([entry({ commission_amount: ["10.00", "12.50"] })]));
      }),
    );
    renderWithProviders(<AuditHistory entityType="properties.propertyfinance" entityId={5} />);
    await waitFor(() => expect(screen.getByText("Commission amount")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-05-01" } });
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "2026-05-31" } });

    await waitFor(() => {
      const params = new URL(urls.at(-1)!).searchParams;
      expect(params.get("created_after")).toBe("2026-05-01");
      expect(params.get("created_before")).toBe("2026-05-31T23:59:59");
    });
  });

  it("renders a merge banner with the target record and reassignment count", async () => {
    server.use(
      http.get("/api/v1/audit-log", () =>
        HttpResponse.json(
          listResponse([
            entry(
              {
                __deleted__: true,
                __merged_into__: "42",
                __rewrites__: { "reservations.Booking.guest": 3 },
                email: ["a@b.com", null],
              },
              { id: "m", entity_type: "accounts.person", object_id: "7" },
            ),
          ]),
        ),
      ),
    );
    renderWithProviders(<AuditHistory entityType="accounts.person" entityId={7} />);

    expect(await screen.findByText("Merged")).toBeInTheDocument();
    expect(screen.getByText(/merged into record #42/i)).toBeInTheDocument();
    expect(screen.getByText(/3 references reassigned/i)).toBeInTheDocument();
  });
});
