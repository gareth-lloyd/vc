import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
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

const existingBlock: EditableBlock = {
  id: 42,
  reason: "owner_block",
  date_from: "2026-06-10",
  date_to: "2026-06-17",
  notes: "Owner stay",
};

describe("AvailabilityBlockFormDialog", () => {
  it("creates a block on save", async () => {
    setReservationsUser();
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
    await userEvent.type(await screen.findByLabelText(/^From$/i), "2026-06-01");
    await userEvent.type(screen.getByLabelText(/^To$/i), "2026-06-05");
    await userEvent.click(screen.getByRole("button", { name: /save block/i }));
    await waitFor(() => expect(body).not.toBeNull());
    expect((body as { date_from?: string }).date_from).toBe("2026-06-01");
    useAuthStore.getState().clear();
  });

  it("shows an inclusive nights summary as dates are entered", async () => {
    setReservationsUser();
    renderWithProviders(
      <AvailabilityBlockFormDialog propertyId={7} open mode="create" onOpenChange={() => {}} />,
    );
    await userEvent.type(await screen.findByLabelText(/^From$/i), "2026-06-10");
    await userEvent.type(screen.getByLabelText(/^To$/i), "2026-06-17");
    // [10 Jun, 17 Jun) is 7 nights ending the 16th — never "17 Jun".
    expect(await screen.findByTestId("block-nights-summary")).toHaveTextContent(
      "7 nights (10–16 Jun 2026)",
    );
    useAuthStore.getState().clear();
  });

  it("shows an inline error when date_to is not after date_from", async () => {
    setReservationsUser();
    renderWithProviders(
      <AvailabilityBlockFormDialog propertyId={7} open mode="create" onOpenChange={() => {}} />,
    );
    await userEvent.type(await screen.findByLabelText(/^From$/i), "2026-06-05");
    await userEvent.type(screen.getByLabelText(/^To$/i), "2026-06-05");
    await userEvent.click(screen.getByRole("button", { name: /save block/i }));
    await waitFor(() =>
      expect(screen.getByText("properties:errors.block_to_before_from")).toBeInTheDocument(),
    );
    useAuthStore.getState().clear();
  });

  it("surfaces a 409 overlap as a top-level error and keeps the dialog open", async () => {
    setReservationsUser();
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
    await userEvent.type(await screen.findByLabelText(/^From$/i), "2026-06-01");
    await userEvent.type(screen.getByLabelText(/^To$/i), "2026-06-05");
    await userEvent.click(screen.getByRole("button", { name: /save block/i }));
    await waitFor(() => expect(screen.getByText(/overlapping live hold/i)).toBeInTheDocument());
    useAuthStore.getState().clear();
  });

  it("submits a PATCH with updated fields on edit", async () => {
    setReservationsUser();
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
    const notes = await screen.findByLabelText(/^Notes$/i);
    await userEvent.clear(notes);
    await userEvent.type(notes, "Updated");
    await userEvent.click(screen.getByRole("button", { name: /save block/i }));
    await waitFor(() => expect(patchBody).not.toBeNull());
    expect((patchBody as { notes?: string }).notes).toBe("Updated");
    useAuthStore.getState().clear();
  });
});
