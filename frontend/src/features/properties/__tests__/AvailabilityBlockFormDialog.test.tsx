import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { blockCalendarHandlers } from "@/test/msw/handlers";
import { renderWithProviders } from "@/test/render";
import { expectTriggerRange, openDateRange, typeDateRange } from "@/test/dateRange";
import { useAuthStore } from "@/features/auth/store";
import {
  AvailabilityBlockFormDialog,
  type EditableBlock,
} from "../components/AvailabilityBlockFormDialog";

function setReservationsUser() {
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
}

// Kept inside the dialog's availability window (frozen today → +18 months) so
// the fixture stays producible by the real API.
const existingBlock: EditableBlock = {
  id: 42,
  reason: "owner_block",
  date_from: "2026-07-10",
  date_to: "2026-07-17",
  notes: "Owner stay",
};

beforeEach(() => {
  server.use(...blockCalendarHandlers);
  // Anchor the empty picker's default month (July 2026) so calendar-click
  // tests don't depend on the real date.
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(new Date(2026, 6, 2));
});

afterEach(() => {
  vi.useRealTimers();
  useAuthStore.getState().clear();
});

describe("AvailabilityBlockFormDialog", () => {
  it("creates a block on save", async () => {
    setReservationsUser();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    let body: unknown = null;
    server.use(
      http.post("/api/v1/properties/7/availability", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(
          { id: 1, property: 7, date_from: "2026-06-01", date_to: "2026-06-05", reason: "manual" },
          { status: 201 },
        );
      }),
    );
    renderWithProviders(
      <AvailabilityBlockFormDialog propertyId={7} open mode="create" onOpenChange={() => {}} />,
    );
    const picker = await openDateRange(user, /^dates/i);
    await typeDateRange(user, picker, { from: "2026-06-01", to: "2026-06-05" });
    expectTriggerRange(/^dates/i, "1–5 Jun 2026 · 4 nights");
    await user.click(screen.getByRole("button", { name: /save block/i }));
    await waitFor(() => expect(body).not.toBeNull());
    expect((body as { date_from?: string }).date_from).toBe("2026-06-01");
  });

  it("shows an inclusive nights summary as dates are entered", async () => {
    setReservationsUser();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithProviders(
      <AvailabilityBlockFormDialog propertyId={7} open mode="create" onOpenChange={() => {}} />,
    );
    const picker = await openDateRange(user, /^dates/i);
    await typeDateRange(user, picker, { from: "2026-06-10", to: "2026-06-17" });
    // [10 Jun, 17 Jun) is 7 nights ending the 16th — never "17 Jun". The
    // dialog-level line stays visible with the popover closed.
    expect(await screen.findByTestId("block-nights-summary")).toHaveTextContent(
      "7 nights (10–16 Jun 2026)",
    );
  });

  it("stores a half-open range from an inclusive calendar selection", async () => {
    setReservationsUser();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    let body: unknown = null;
    server.use(
      http.post("/api/v1/properties/7/availability", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(
          { id: 1, property: 7, date_from: "2026-07-21", date_to: "2026-07-26", reason: "manual" },
          { status: 201 },
        );
      }),
    );
    renderWithProviders(
      <AvailabilityBlockFormDialog propertyId={7} open mode="create" onOpenChange={() => {}} />,
    );
    const picker = await openDateRange(user, /^dates/i);
    await user.click(picker.getByRole("button", { name: /21 july 2026/i }));
    await user.click(picker.getByRole("button", { name: /25 july 2026/i }));
    await user.click(screen.getByRole("button", { name: /save block/i }));
    await waitFor(() => expect(body).not.toBeNull());
    // Inclusive nights 21–25 → stored half-open with checkout the 26th.
    expect(body).toMatchObject({ date_from: "2026-07-21", date_to: "2026-07-26" });
  });

  it("greys out an occupied day in the calendar picker", async () => {
    setReservationsUser();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    server.use(
      http.get("/api/v1/properties/7/availability", () =>
        HttpResponse.json({
          property_id: 7,
          cells: [{ date: "2026-07-23", available: false, reason: "booked" }],
        }),
      ),
    );
    renderWithProviders(
      <AvailabilityBlockFormDialog propertyId={7} open mode="create" onOpenChange={() => {}} />,
    );
    // Opening the picker triggers the deferred availability fetch.
    const picker = await openDateRange(user, /^dates/i);
    await waitFor(() =>
      expect(picker.getByRole("button", { name: /23 july 2026/i })).toBeDisabled(),
    );
  });

  it("collapses a calendar selection spanning an occupied day to the clicked day", async () => {
    setReservationsUser();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    server.use(
      http.get("/api/v1/properties/7/availability", () =>
        HttpResponse.json({
          property_id: 7,
          cells: [{ date: "2026-07-23", available: false, reason: "booked" }],
        }),
      ),
    );
    renderWithProviders(
      <AvailabilityBlockFormDialog propertyId={7} open mode="create" onOpenChange={() => {}} />,
    );
    const picker = await openDateRange(user, /^dates/i);
    await waitFor(() =>
      expect(picker.getByRole("button", { name: /23 july 2026/i })).toBeDisabled(),
    );
    await user.click(picker.getByRole("button", { name: /21 july 2026/i }));
    // 21 → 25 would span the booked 23rd: excludeDisabled resets the
    // selection to the clicked day instead of straddling the booking.
    await user.click(picker.getByRole("button", { name: /25 july 2026/i }));
    expectTriggerRange(/^dates/i, "25–26 Jul 2026 · 1 night");
  });

  it("keeps the edited block's own days selectable", async () => {
    setReservationsUser();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    server.use(
      http.get("/api/v1/properties/7/availability", () =>
        HttpResponse.json({
          property_id: 7,
          cells: [
            // The block being edited (id 42) covers these days; they must stay
            // selectable. An unrelated occupied day must still be disabled.
            { date: "2026-07-12", available: false, reason: "owner_block", block_id: 42 },
            { date: "2026-07-20", available: false, reason: "booked", block_id: null },
          ],
        }),
      ),
    );
    renderWithProviders(
      <AvailabilityBlockFormDialog
        propertyId={7}
        open
        mode="edit"
        block={existingBlock}
        onOpenChange={() => {}}
      />,
    );
    const picker = await openDateRange(user, /^dates/i);
    await waitFor(() =>
      expect(picker.getByRole("button", { name: /20 july 2026/i })).toBeDisabled(),
    );
    expect(picker.getByRole("button", { name: /12 july 2026/i })).toBeEnabled();
  });

  it("shows an inline error when date_to is not after date_from", async () => {
    setReservationsUser();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithProviders(
      <AvailabilityBlockFormDialog propertyId={7} open mode="create" onOpenChange={() => {}} />,
    );
    const picker = await openDateRange(user, /^dates/i);
    await typeDateRange(user, picker, { from: "2026-06-05", to: "2026-06-05" });
    // Save sits outside the popover, so this click also closes the picker —
    // the zod error must still be visible next to the trigger.
    await user.click(screen.getByRole("button", { name: /save block/i }));
    await waitFor(() =>
      expect(screen.getByText("To date must be after From date")).toBeInTheDocument(),
    );
  });

  it("surfaces a 409 overlap as a top-level error and keeps the dialog open", async () => {
    setReservationsUser();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    server.use(
      http.post("/api/v1/properties/7/availability", () =>
        HttpResponse.json(
          {
            code: "hold_unavailable",
            detail: "An overlapping live hold already exists",
            field_errors: {},
          },
          { status: 409 },
        ),
      ),
    );
    renderWithProviders(
      <AvailabilityBlockFormDialog propertyId={7} open mode="create" onOpenChange={() => {}} />,
    );
    const picker = await openDateRange(user, /^dates/i);
    await typeDateRange(user, picker, { from: "2026-06-01", to: "2026-06-05" });
    await user.click(screen.getByRole("button", { name: /save block/i }));
    await waitFor(() => expect(screen.getByText(/overlapping live hold/i)).toBeInTheDocument());
  });

  it("submits a PATCH with updated fields on edit", async () => {
    setReservationsUser();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    let patchBody: unknown = null;
    server.use(
      http.patch("/api/v1/availability/42", async ({ request }) => {
        patchBody = await request.json();
        return HttpResponse.json({ ...existingBlock, property: 7, notes: "Updated" });
      }),
    );
    renderWithProviders(
      <AvailabilityBlockFormDialog
        propertyId={7}
        open
        mode="edit"
        block={existingBlock}
        onOpenChange={() => {}}
      />,
    );
    // The trigger is seeded with the stored half-open range.
    expectTriggerRange(/^dates/i, "10–17 Jul 2026 · 7 nights");
    const notes = await screen.findByLabelText(/^Notes$/i);
    await user.clear(notes);
    await user.type(notes, "Updated");
    await user.click(screen.getByRole("button", { name: /save block/i }));
    await waitFor(() => expect(patchBody).not.toBeNull());
    expect((patchBody as { notes?: string }).notes).toBe("Updated");
  });
});
