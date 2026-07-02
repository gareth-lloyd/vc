import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { blockCalendarHandlers } from "@/test/msw/handlers";
import { renderWithProviders } from "@/test/render";
import { clickDateRange, expectTriggerRange, openDateRange, typeDateRange } from "@/test/dateRange";
import { BlockRequestDialog } from "../BlockRequestDialog";

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
    info: vi.fn(),
  },
}));

function created(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    property: 3,
    date_from: "2026-08-01",
    date_to: "2026-08-08",
    kind: "owner_stay",
    notes: "",
    status: "approved",
    created_at: "2026-06-03T10:00:00Z",
    ...overrides,
  };
}

beforeEach(() => {
  toastSuccess.mockClear();
  toastError.mockClear();
  server.use(...blockCalendarHandlers);
  // Anchor the empty picker's default month (July 2026) so calendar-click
  // tests don't depend on the real date.
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(new Date(2026, 6, 2));
});

afterEach(() => {
  vi.useRealTimers();
  server.resetHandlers();
});

describe("BlockRequestDialog", () => {
  it("rejects a non-forward date range with an inline error", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithProviders(<BlockRequestDialog propertyId={3} open onOpenChange={() => {}} />);

    const picker = await openDateRange(user, /^dates/i);
    await typeDateRange(user, picker, { from: "2026-08-08", to: "2026-08-01" });
    // Submit sits outside the popover, so this click also closes the picker —
    // the zod error must still be visible next to the trigger.
    await user.click(screen.getByRole("button", { name: /block dates/i }));

    expect(await screen.findByText(/end date must be after/i)).toBeInTheDocument();
  });

  it("shows an inclusive nights summary as dates are entered", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithProviders(<BlockRequestDialog propertyId={3} open onOpenChange={() => {}} />);

    const picker = await openDateRange(user, /^dates/i);
    await typeDateRange(user, picker, { from: "2026-08-01", to: "2026-08-08" });

    // [1 Aug, 8 Aug) is 7 nights — the summary must not surface the exclusive
    // 8th. The dialog-level line stays visible with the popover closed.
    expect(await screen.findByTestId("block-nights-summary")).toHaveTextContent(
      "7 nights (1–7 Aug 2026)",
    );
  });

  it("posts the request and toasts on success", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    let body: unknown = null;
    server.use(
      http.post("/api/v1/owner/block-requests", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(created(), { status: 201 });
      }),
    );
    const onOpenChange = vi.fn();
    renderWithProviders(<BlockRequestDialog propertyId={3} open onOpenChange={onOpenChange} />);

    const picker = await openDateRange(user, /^dates/i);
    await typeDateRange(user, picker, { from: "2026-08-01", to: "2026-08-08" });
    await user.click(screen.getByRole("button", { name: /block dates/i }));

    await waitFor(() =>
      expect(body).toMatchObject({
        property: 3,
        kind: "owner_stay",
        date_from: "2026-08-01",
        date_to: "2026-08-08",
      }),
    );
    await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("stores a half-open range from an inclusive calendar selection", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    let body: unknown = null;
    server.use(
      http.post("/api/v1/owner/block-requests", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(created(), { status: 201 });
      }),
    );
    renderWithProviders(<BlockRequestDialog propertyId={3} open onOpenChange={() => {}} />);

    // Pick first and last night on the calendar — the user never enters the
    // exclusive checkout date.
    const picker = await openDateRange(user, /^dates/i);
    await clickDateRange(user, picker, /21 july 2026/i, /25 july 2026/i);
    expectTriggerRange(/^dates/i, "21–26 Jul 2026 · 5 nights");
    await user.click(screen.getByRole("button", { name: /^block dates$/i }));

    await waitFor(() => expect(body).not.toBeNull());
    // Inclusive nights 21–25 → stored half-open with checkout the 26th.
    expect(body).toMatchObject({ date_from: "2026-07-21", date_to: "2026-07-26" });
  });

  it("defers the availability fetch until the picker opens, then greys out an occupied day", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    let calendarCalls = 0;
    server.use(
      http.get("/api/v1/owner/properties/3/calendar", () => {
        calendarCalls += 1;
        return HttpResponse.json({
          property_id: 3,
          can_request_block: true,
          cells: [{ date: "2026-07-23", available: false, reason: "booked" }],
        });
      }),
    );
    renderWithProviders(<BlockRequestDialog propertyId={3} open onOpenChange={() => {}} />);

    // The list only feeds the calendar popover — no fetch on mount.
    expect(await screen.findByRole("button", { name: /^dates/i })).toBeInTheDocument();
    expect(calendarCalls).toBe(0);

    const picker = await openDateRange(user, /^dates/i);
    await waitFor(() =>
      expect(picker.getByRole("button", { name: /23 july 2026/i })).toBeDisabled(),
    );
    expect(calendarCalls).toBeGreaterThan(0);
  });

  it("maps a 409 conflict to a top-level alert and stays open", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    server.use(
      http.post("/api/v1/owner/block-requests", () =>
        HttpResponse.json(
          { code: "overlapping_booking", detail: "A booking already occupies those dates" },
          { status: 409 },
        ),
      ),
    );
    const onOpenChange = vi.fn();
    renderWithProviders(<BlockRequestDialog propertyId={3} open onOpenChange={onOpenChange} />);

    const picker = await openDateRange(user, /^dates/i);
    await typeDateRange(user, picker, { from: "2026-08-01", to: "2026-08-08" });
    await user.click(screen.getByRole("button", { name: /block dates/i }));

    expect(await screen.findByText(/overlap an existing booking or block/i)).toBeInTheDocument();
    expect(onOpenChange).not.toHaveBeenCalled();
    expect(toastError).not.toHaveBeenCalled();
  });

  it("toasts on a 5xx server error", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    server.use(
      http.post("/api/v1/owner/block-requests", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    renderWithProviders(<BlockRequestDialog propertyId={3} open onOpenChange={() => {}} />);

    const picker = await openDateRange(user, /^dates/i);
    await typeDateRange(user, picker, { from: "2026-08-01", to: "2026-08-08" });
    await user.click(screen.getByRole("button", { name: /block dates/i }));

    await waitFor(() => expect(toastError).toHaveBeenCalled());
  });
});
