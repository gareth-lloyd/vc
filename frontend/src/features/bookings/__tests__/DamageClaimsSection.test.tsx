import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { drfPage } from "@/test/drf";
import { renderWithProviders } from "@/test/render";
import { DamageClaimsSection } from "../components/DamageClaimsSection";
import type { DamageClaim } from "../schemas";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { toast } from "sonner";

const BOOKING_ID = 51;

function makeClaim(overrides: Partial<DamageClaim> = {}): DamageClaim {
  return {
    id: 7,
    reference: "DC-000007",
    booking: BOOKING_ID,
    amount: "500.00",
    description: "Broken window",
    status: "open",
    currency: 1,
    currency_code: "GBP",
    itemized_lines: [],
    photos: [],
    accepted_by_guest_at: null,
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-01T00:00:00Z",
    ...overrides,
  };
}

function listHandler(rows: DamageClaim[]) {
  return http.get(`/api/v1/bookings/${BOOKING_ID}/damage-claims`, () =>
    HttpResponse.json(drfPage(rows)),
  );
}

beforeEach(() => {
  vi.mocked(toast.success).mockClear();
  vi.mocked(toast.error).mockClear();
});

afterEach(() => {
  server.resetHandlers();
});

function setup(canWrite = true) {
  return renderWithProviders(
    <DamageClaimsSection bookingId={BOOKING_ID} currency="GBP" canWrite={canWrite} />,
  );
}

describe("DamageClaimsSection", () => {
  it("renders claim rows with reference, amount and status", async () => {
    server.use(listHandler([makeClaim()]));
    setup();

    expect(await screen.findByText("DC-000007")).toBeInTheDocument();
    expect(screen.getByText("Broken window")).toBeInTheDocument();
    expect(screen.getByText("£500.00")).toBeInTheDocument();
    expect(screen.getByText("Open")).toBeInTheDocument();
  });

  it("shows an empty state when there are no claims", async () => {
    server.use(listHandler([]));
    setup();

    expect(await screen.findByText(/no damage claims/i)).toBeInTheDocument();
  });

  it("withdraws a claim and refreshes the list", async () => {
    let withdrew = false;
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}/damage-claims`, () =>
        HttpResponse.json(drfPage([makeClaim({ status: withdrew ? "withdrawn" : "open" })])),
      ),
      http.post(`/api/v1/bookings/${BOOKING_ID}/damage-claims/7:withdraw`, () => {
        withdrew = true;
        return HttpResponse.json(makeClaim({ status: "withdrawn" }));
      }),
    );
    setup();

    await userEvent.click(await screen.findByRole("button", { name: /withdraw claim DC-000007/i }));
    // Confirm dialog
    await userEvent.click(screen.getByRole("button", { name: "Withdraw claim" }));

    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(await screen.findByText("Withdrawn")).toBeInTheDocument();
  });

  it("disables the file button without the write role", async () => {
    server.use(listHandler([]));
    setup(false);

    const fileButton = await screen.findByRole("button", { name: /file claim/i });
    expect(fileButton).toBeDisabled();
  });

  it("approves an open claim and flips the badge", async () => {
    let approved = false;
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}/damage-claims`, () =>
        HttpResponse.json(drfPage([makeClaim({ status: approved ? "approved" : "open" })])),
      ),
      http.post(`/api/v1/bookings/${BOOKING_ID}/damage-claims/7:approve`, () => {
        approved = true;
        return HttpResponse.json(makeClaim({ status: "approved" }));
      }),
    );
    setup();

    await userEvent.click(await screen.findByRole("button", { name: /approve claim DC-000007/i }));
    await userEvent.click(screen.getByRole("button", { name: "Approve claim" }));

    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(await screen.findByText("Approved")).toBeInTheDocument();
  });

  it("offers edit + approve + withdraw on an open claim", async () => {
    server.use(listHandler([makeClaim({ status: "open" })]));
    setup();

    expect(
      await screen.findByRole("button", { name: /edit claim DC-000007/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /approve claim DC-000007/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /withdraw claim DC-000007/i })).toBeInTheDocument();
  });

  it("hides edit + approve but keeps withdraw once approved", async () => {
    server.use(listHandler([makeClaim({ status: "approved" })]));
    setup();

    expect(await screen.findByText("Approved")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /edit claim DC-000007/i })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /approve claim DC-000007/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /withdraw claim DC-000007/i })).toBeInTheDocument();
  });

  it("shows no row actions on a settled claim", async () => {
    server.use(listHandler([makeClaim({ status: "settled" })]));
    setup();

    expect(await screen.findByText("Settled")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /edit claim DC-000007/i })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /approve claim DC-000007/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /withdraw claim DC-000007/i }),
    ).not.toBeInTheDocument();
  });

  it("surfaces the backend detail when approve 409s", async () => {
    server.use(
      listHandler([makeClaim({ status: "open" })]),
      http.post(`/api/v1/bookings/${BOOKING_ID}/damage-claims/7:approve`, () =>
        HttpResponse.json(
          { detail: "Cannot move a settled claim to approved.", code: "invalid_transition" },
          { status: 409 },
        ),
      ),
    );
    setup();

    await userEvent.click(await screen.findByRole("button", { name: /approve claim DC-000007/i }));
    await userEvent.click(screen.getByRole("button", { name: "Approve claim" }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Cannot move a settled claim to approved."),
    );
  });
});
