import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import { RoomFormDialog } from "../components/RoomFormDialog";
import type { PropertyRoom } from "../schemas";

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

const existingRoom: PropertyRoom = {
  id: 200,
  property: 7,
  name: "Master bedroom",
  placement: "main_house",
  website_description: "",
  vc_notes: "",
  is_ensuite: true,
  sort_order: 0,
  beds: {
    double: 1,
    twin_double: 0,
    twin: 0,
    single: 0,
    bunk: 0,
    sofa: 0,
    childrens: 0,
  },
};

describe("RoomFormDialog", () => {
  it("submits a new room on save (create)", async () => {
    setReservationsUser();
    let postedBody: unknown = null;
    server.use(
      http.post("/api/v1/properties/7/rooms", async ({ request }) => {
        postedBody = await request.json();
        return HttpResponse.json({ ...existingRoom, id: 999, name: "New room" }, { status: 201 });
      }),
    );
    const onOpenChange = (open: boolean) => {
      void open;
    };
    renderWithProviders(
      <RoomFormDialog propertyId={7} open mode="create" onOpenChange={onOpenChange} />,
    );
    const name = await screen.findByLabelText(/^Name$/i);
    await userEvent.type(name, "New room");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(postedBody).not.toBeNull());
    expect((postedBody as { name?: string }).name).toBe("New room");
    useAuthStore.getState().clear();
  });

  it("maps 4xx field_errors onto inline form errors and shows top-level detail", async () => {
    setReservationsUser();
    server.use(
      http.post("/api/v1/properties/7/rooms", () =>
        HttpResponse.json(
          {
            code: "validation_error",
            detail: "Validation failed",
            field_errors: { name: ["Name is too short"] },
          },
          { status: 400 },
        ),
      ),
    );
    renderWithProviders(
      <RoomFormDialog propertyId={7} open mode="create" onOpenChange={() => {}} />,
    );
    const name = await screen.findByLabelText(/^Name$/i);
    await userEvent.type(name, "x");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(screen.getByText(/Name is too short/i)).toBeInTheDocument());
    expect(screen.getByText(/Validation failed/i)).toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("submits a PATCH with updated fields on save (edit)", async () => {
    setReservationsUser();
    let patchBody: unknown = null;
    server.use(
      http.patch("/api/v1/properties/7/rooms/200", async ({ request }) => {
        patchBody = await request.json();
        return HttpResponse.json({ ...existingRoom, name: "Master suite" });
      }),
    );
    renderWithProviders(
      <RoomFormDialog
        propertyId={7}
        open
        mode="edit"
        room={existingRoom}
        onOpenChange={() => {}}
      />,
    );
    const name = await screen.findByLabelText(/^Name$/i);
    await userEvent.clear(name);
    await userEvent.type(name, "Master suite");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(patchBody).not.toBeNull());
    expect((patchBody as { name?: string }).name).toBe("Master suite");
    useAuthStore.getState().clear();
  });
});
