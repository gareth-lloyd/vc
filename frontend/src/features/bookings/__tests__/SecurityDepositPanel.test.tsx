import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { drfPage } from "@/test/drf";
import { renderWithProviders } from "@/test/render";
import { SecurityDepositPanel } from "../components/SecurityDepositPanel";
import type { DamageClaim, SecurityDeposit } from "../schemas";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { toast } from "sonner";

const BOOKING_ID = 51;

function makeDeposit(overrides: Partial<SecurityDeposit> = {}): SecurityDeposit {
  return {
    id: 9,
    reference: "SD-000009",
    kind: "pre_auth_hold",
    status: "pre_authed",
    amount: "500.00",
    currency_code: "GBP",
    hold_expires_at: "2026-07-01T00:00:00Z",
    due_at: null,
    release_scheduled_for: null,
    captured_amount: null,
    refunded_amount: null,
    damage_claim: null,
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-01T00:00:00Z",
    ...overrides,
  };
}

function makeClaim(overrides: Partial<DamageClaim> = {}): DamageClaim {
  return {
    id: 7,
    reference: "DC-000007",
    booking: BOOKING_ID,
    amount: "120.00",
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

function depositHandler(deposit: SecurityDeposit | null) {
  return http.get(`/api/v1/bookings/${BOOKING_ID}/security/deposit`, () =>
    HttpResponse.json(deposit),
  );
}

function claimsHandler(rows: DamageClaim[]) {
  return http.get(`/api/v1/bookings/${BOOKING_ID}/damage-claims`, () =>
    HttpResponse.json(drfPage(rows)),
  );
}

const trackResponse = {
  booking: BOOKING_ID,
  purpose: "security_deposit",
  scheduled_amount: "500.00",
  paid_amount: "0.00",
  due_at: null,
  status: "succeeded",
};

beforeEach(() => {
  vi.mocked(toast.success).mockClear();
  vi.mocked(toast.error).mockClear();
});

afterEach(() => {
  server.resetHandlers();
});

function setup(canWrite = true) {
  return renderWithProviders(
    <SecurityDepositPanel bookingId={BOOKING_ID} currency="GBP" canWrite={canWrite} />,
  );
}

describe("SecurityDepositPanel", () => {
  it("renders the deposit reference, kind, status and amount", async () => {
    server.use(depositHandler(makeDeposit()));
    setup();

    expect(await screen.findByText("SD-000009")).toBeInTheDocument();
    expect(screen.getByText("Card pre-authorisation")).toBeInTheDocument();
    expect(screen.getByText("Pre-authorised")).toBeInTheDocument();
    expect(screen.getByText("£500.00")).toBeInTheDocument();
  });

  it("shows an empty state when there is no deposit", async () => {
    server.use(depositHandler(null));
    setup();

    expect(await screen.findByText("No security deposit")).toBeInTheDocument();
  });

  it("renders the captured amount on a terminal CAPTURED deposit", async () => {
    server.use(
      depositHandler(
        makeDeposit({ status: "captured", captured_amount: "120.00", hold_expires_at: null }),
      ),
    );
    setup();

    expect(await screen.findByText("Captured")).toBeInTheDocument();
    expect(screen.getByText("£120.00")).toBeInTheDocument();
  });

  it("hides the action buttons on a terminal deposit", async () => {
    server.use(depositHandler(makeDeposit({ status: "released" })));
    setup();

    await screen.findByText("SD-000009");
    expect(screen.queryByRole("button", { name: "Release" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Capture for damages" })).not.toBeInTheDocument();
  });

  it("disables actions for non-accounts staff but still shows the panel", async () => {
    server.use(depositHandler(makeDeposit()));
    setup(false);

    expect(await screen.findByText("SD-000009")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Release" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Capture for damages" })).toBeDisabled();
  });

  it("releases the deposit through the confirm dialog", async () => {
    const user = userEvent.setup();
    let released = false;
    server.use(
      depositHandler(makeDeposit()),
      http.post(`/api/v1/bookings/${BOOKING_ID}/security:release`, () => {
        released = true;
        return HttpResponse.json(trackResponse);
      }),
    );
    setup();

    await user.click(await screen.findByRole("button", { name: "Release" }));
    await user.click(await screen.findByRole("button", { name: "Release deposit" }));

    await waitFor(() => expect(released).toBe(true));
    expect(toast.success).toHaveBeenCalledWith("Security deposit released");
  });

  it("captures against an open claim, posting damage_claim + captured_amount", async () => {
    const user = userEvent.setup();
    let body: Record<string, unknown> | null = null;
    server.use(
      depositHandler(makeDeposit()),
      claimsHandler([makeClaim()]),
      http.post(`/api/v1/bookings/${BOOKING_ID}/security:claim`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(trackResponse);
      }),
    );
    setup();

    await user.click(await screen.findByRole("button", { name: "Capture for damages" }));

    // Pick the open claim from the select.
    await user.click(await screen.findByRole("combobox"));
    await user.click(await screen.findByRole("option", { name: /DC-000007/ }));

    await user.click(screen.getByRole("button", { name: "Capture" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toEqual({ damage_claim: 7, captured_amount: "120.00" });
    expect(toast.success).toHaveBeenCalledWith("Captured against the deposit");
  });
});
