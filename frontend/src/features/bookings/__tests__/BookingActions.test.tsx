import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, waitFor, within } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { queryKeys } from "@/lib/query/keys";
import { QueryClient } from "@tanstack/react-query";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import { BookingActions } from "../components/BookingActions";
import type { BookingDetail } from "../schemas";
import type { UserMe } from "@/features/auth/schemas";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { toast } from "sonner";

const BOOKING_ID = 51;

function makeUser(overrides: Partial<UserMe> = {}): UserMe {
  return {
    id: 1,
    email: "u@v.com",
    first_name: "U",
    last_name: "V",
    is_active: true,
    is_staff: true,
    is_superuser: false,
    ...overrides,
  };
}

function makeBookingDetail(overrides: Partial<BookingDetail> = {}): BookingDetail {
  return {
    id: BOOKING_ID,
    reference: "B-AAA-001",
    status: "draft",
    property: 12,
    guest: 99,
    agent: null,
    assigned_to: null,
    date_from: "2026-07-01",
    date_to: "2026-07-08",
    adults: 4,
    children: 2,
    currency: 1,
    rental_price: "1500.00",
    balance_due: "1000.00",
    balance_due_at: "2026-06-01",
    site_source: "main_website",
    is_archived: false,
    archived_at: null,
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-02T00:00:00Z",
    ...overrides,
  };
}

function asReservationsUser() {
  useAuthStore.getState().setMe(makeUser(), {
    role: "RESERVATIONS",
    is_superuser: false,
    permissions: [],
  });
}

function asViewerUser() {
  useAuthStore.getState().setMe(makeUser(), {
    role: "VIEWER",
    is_superuser: false,
    permissions: [],
  });
}

beforeEach(() => {
  useAuthStore.getState().clear();
  vi.mocked(toast.success).mockClear();
  vi.mocked(toast.error).mockClear();
});

afterEach(() => {
  server.resetHandlers();
});

describe("BookingActions — disabled-state matrix", () => {
  it("disables all primary buttons and the dropdown trigger when the user lacks the reservations role", () => {
    asViewerUser();
    renderWithProviders(<BookingActions booking={makeBookingDetail({ status: "draft" })} />);
    expect(screen.getByRole("button", { name: /confirm booking/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /cancel booking/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /owner decline/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /more actions/i })).toBeDisabled();
  });

  it("disables confirm but enables cancel on a status outside the confirm whitelist", () => {
    asReservationsUser();
    renderWithProviders(
      <BookingActions booking={makeBookingDetail({ status: "awaiting_deposit" })} />,
    );
    expect(screen.getByRole("button", { name: /confirm booking/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /cancel booking/i })).toBeEnabled();
  });

  it("disables both on a terminal status", () => {
    asReservationsUser();
    renderWithProviders(<BookingActions booking={makeBookingDetail({ status: "checked_out" })} />);
    expect(screen.getByRole("button", { name: /confirm booking/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /cancel booking/i })).toBeDisabled();
  });

  it("enables both on a draft booking with a reservations user", () => {
    asReservationsUser();
    renderWithProviders(<BookingActions booking={makeBookingDetail({ status: "draft" })} />);
    expect(screen.getByRole("button", { name: /confirm booking/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /cancel booking/i })).toBeEnabled();
  });
});

function createCachingClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity, staleTime: 0 },
      mutations: { retry: false },
    },
  });
}

describe("BookingActions — confirm flow", () => {
  it("opens the confirm dialog, POSTs on confirm, updates detail cache, toasts success", async () => {
    asReservationsUser();
    const user = userEvent.setup();
    const queryClient = createCachingClient();
    queryClient.setQueryData(
      queryKeys.bookings.detail(BOOKING_ID),
      makeBookingDetail({ status: "draft" }),
    );

    server.use(
      http.post(`/api/v1/bookings/${BOOKING_ID}:confirm`, () =>
        HttpResponse.json(makeBookingDetail({ status: "awaiting_deposit" })),
      ),
    );

    renderWithProviders(<BookingActions booking={makeBookingDetail({ status: "draft" })} />, {
      queryClient,
    });

    await user.click(screen.getByRole("button", { name: /confirm booking/i }));

    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /^confirm$/i }));

    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(
      queryClient.getQueryData<BookingDetail>(queryKeys.bookings.detail(BOOKING_ID))?.status,
    ).toBe("awaiting_deposit");
  });
});

describe("BookingActions — cancel flow", () => {
  it("submits the typed reason and toasts success", async () => {
    asReservationsUser();
    const user = userEvent.setup();
    const queryClient = createCachingClient();
    queryClient.setQueryData(
      queryKeys.bookings.detail(BOOKING_ID),
      makeBookingDetail({ status: "deposit_paid" }),
    );

    let receivedBody: unknown = null;
    server.use(
      http.post(`/api/v1/bookings/${BOOKING_ID}:cancel`, async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json(
          makeBookingDetail({
            status: "cancelled",
            cancel_reason: "no-show",
          }),
        );
      }),
    );

    renderWithProviders(
      <BookingActions booking={makeBookingDetail({ status: "deposit_paid" })} />,
      { queryClient },
    );

    await user.click(screen.getByRole("button", { name: /cancel booking/i }));
    const dialog = await screen.findByRole("dialog");
    const reason = within(dialog).getByLabelText(/reason/i);
    await user.type(reason, "no-show");
    await user.click(within(dialog).getByRole("button", { name: /^cancel booking$/i }));

    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(receivedBody).toEqual({ reason: "no-show" });
  });

  it("blocks client-side when reason exceeds 500 characters", async () => {
    asReservationsUser();
    const user = userEvent.setup();
    const networkCalls = vi.fn();
    server.use(
      http.post(`/api/v1/bookings/${BOOKING_ID}:cancel`, () => {
        networkCalls();
        return HttpResponse.json(makeBookingDetail({ status: "cancelled" }));
      }),
    );

    renderWithProviders(<BookingActions booking={makeBookingDetail({ status: "draft" })} />);

    await user.click(screen.getByRole("button", { name: /cancel booking/i }));
    const dialog = await screen.findByRole("dialog");
    const reason = within(dialog).getByLabelText(/reason/i);
    await user.click(reason);
    await user.paste("x".repeat(501));
    await user.click(within(dialog).getByRole("button", { name: /^cancel booking$/i }));

    expect(await within(dialog).findByText(/under 500 characters/i)).toBeInTheDocument();
    expect(networkCalls).not.toHaveBeenCalled();
  });

  it("surfaces a 400 field_errors.reason in the form and does NOT toast", async () => {
    asReservationsUser();
    const user = userEvent.setup();
    server.use(
      http.post(`/api/v1/bookings/${BOOKING_ID}:cancel`, () =>
        HttpResponse.json(
          {
            code: "invalid",
            detail: "Validation failed",
            field_errors: { reason: ["That reason is rejected"] },
          },
          { status: 400 },
        ),
      ),
    );

    renderWithProviders(<BookingActions booking={makeBookingDetail({ status: "draft" })} />);

    await user.click(screen.getByRole("button", { name: /cancel booking/i }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText(/reason/i), "anything");
    await user.click(within(dialog).getByRole("button", { name: /^cancel booking$/i }));

    expect(await within(dialog).findByText(/that reason is rejected/i)).toBeInTheDocument();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("toasts on 500 and leaves the dialog open", async () => {
    asReservationsUser();
    const user = userEvent.setup();
    server.use(
      http.post(`/api/v1/bookings/${BOOKING_ID}:cancel`, () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );

    renderWithProviders(<BookingActions booking={makeBookingDetail({ status: "draft" })} />);

    await user.click(screen.getByRole("button", { name: /cancel booking/i }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText(/reason/i), "x");
    await user.click(within(dialog).getByRole("button", { name: /^cancel booking$/i }));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});

describe("BookingActions — owner decline flow", () => {
  it("opens decline dialog, POSTs typed reason, toasts success", async () => {
    asReservationsUser();
    const user = userEvent.setup();
    const queryClient = createCachingClient();
    queryClient.setQueryData(
      queryKeys.bookings.detail(BOOKING_ID),
      makeBookingDetail({ status: "pending_owner_approval" }),
    );

    let receivedBody: unknown = null;
    server.use(
      http.post(`/api/v1/bookings/${BOOKING_ID}:owner-decline`, async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json(makeBookingDetail({ status: "declined" }));
      }),
    );

    renderWithProviders(
      <BookingActions booking={makeBookingDetail({ status: "pending_owner_approval" })} />,
      { queryClient },
    );

    await user.click(screen.getByRole("button", { name: /owner decline/i }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText(/reason/i), "owner not available");
    await user.click(within(dialog).getByRole("button", { name: /^decline booking$/i }));

    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(receivedBody).toEqual({ reason: "owner not available" });
  });
});

describe("BookingActions — More actions dropdown", () => {
  it("lists secondary actions with status-aware enablement", async () => {
    asReservationsUser();
    const user = userEvent.setup();
    renderWithProviders(<BookingActions booking={makeBookingDetail({ status: "checked_out" })} />);

    await user.click(screen.getByRole("button", { name: /more actions/i }));

    expect(screen.getByRole("menuitem", { name: /archive booking/i })).not.toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.getByRole("menuitem", { name: /modify dates/i })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.getByRole("menuitem", { name: /resend confirmation/i })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
  });

  it("archive action opens a confirm dialog and POSTs on confirm", async () => {
    asReservationsUser();
    const user = userEvent.setup();
    const queryClient = createCachingClient();
    queryClient.setQueryData(
      queryKeys.bookings.detail(BOOKING_ID),
      makeBookingDetail({ status: "checked_out", is_archived: false }),
    );

    let called = false;
    server.use(
      http.post(`/api/v1/bookings/${BOOKING_ID}:archive`, () => {
        called = true;
        return HttpResponse.json(makeBookingDetail({ status: "checked_out", is_archived: true }));
      }),
    );

    renderWithProviders(
      <BookingActions booking={makeBookingDetail({ status: "checked_out", is_archived: false })} />,
      { queryClient },
    );

    await user.click(screen.getByRole("button", { name: /more actions/i }));
    await user.click(screen.getByRole("menuitem", { name: /archive booking/i }));

    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /^archive$/i }));

    await waitFor(() => expect(called).toBe(true));
    expect(toast.success).toHaveBeenCalled();
    expect(
      queryClient.getQueryData<BookingDetail>(queryKeys.bookings.detail(BOOKING_ID))?.is_archived,
    ).toBe(true);
  });

  it("resend confirmation toasts on error", async () => {
    asReservationsUser();
    const user = userEvent.setup();
    server.use(
      http.post(`/api/v1/bookings/${BOOKING_ID}:resend-confirmation`, () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );

    renderWithProviders(
      <BookingActions booking={makeBookingDetail({ status: "awaiting_deposit" })} />,
    );

    await user.click(screen.getByRole("button", { name: /more actions/i }));
    await user.click(screen.getByRole("menuitem", { name: /resend confirmation/i }));

    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /^resend$/i }));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
  });
});
