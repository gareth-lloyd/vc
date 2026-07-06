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
  floor: "",
  placement_note: "",
  website_description: "",
  vc_notes: "",
  is_ensuite: true,
  ensuite_type: "",
  access: "",
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
  attribute_links: [],
};

// Assigned amenities: one live catalog row (Wardrobe, id 1 in the default MSW
// catalog) and one retired row (Fireplace, id 3, is_active=false).
const roomWithAmenities: PropertyRoom = {
  ...existingRoom,
  attribute_links: [
    {
      id: 90,
      attribute: 1,
      slug: "wardrobe",
      name: "Wardrobe",
      icon: "shirt",
      is_active: true,
      note: "walk-in",
    },
    {
      id: 91,
      attribute: 3,
      slug: "fireplace",
      name: "Fireplace",
      icon: "flame",
      is_active: false,
      note: "",
    },
  ],
};

async function choose(comboboxName: RegExp, optionName: RegExp) {
  await userEvent.click(await screen.findByRole("combobox", { name: comboboxName }));
  await userEvent.click(await screen.findByRole("option", { name: optionName }));
}

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

  it("submits facet selects and ticked amenities with notes (create)", async () => {
    setReservationsUser();
    let postedBody: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/properties/7/rooms", async ({ request }) => {
        postedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...existingRoom, id: 999, name: "New room" }, { status: 201 });
      }),
    );
    renderWithProviders(
      <RoomFormDialog propertyId={7} open mode="create" onOpenChange={() => {}} />,
    );
    await userEvent.type(await screen.findByLabelText(/^Name$/i), "New room");
    await choose(/ensuite type/i, /^shower$/i);
    await choose(/^access$/i, /^outside$/i);
    await userEvent.click(await screen.findByRole("checkbox", { name: /^wardrobe$/i }));
    await userEvent.type(screen.getByPlaceholderText(/note \(optional\)/i), "walk-in");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(postedBody).not.toBeNull());
    expect(postedBody).toMatchObject({
      ensuite_type: "shower",
      access: "outside",
      is_ensuite: true,
      attribute_links: [{ attribute: 1, note: "walk-in" }],
    });
    useAuthStore.getState().clear();
  });

  it("shows the double-bed-size select when a double bed is present and posts it (edit)", async () => {
    setReservationsUser();
    let patchBody: { beds?: { double_size?: string } } | null = null;
    server.use(
      http.patch("/api/v1/properties/7/rooms/200", async ({ request }) => {
        patchBody = (await request.json()) as { beds?: { double_size?: string } };
        return HttpResponse.json(existingRoom);
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
    await choose(/double bed size/i, /^super-king$/i);
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(patchBody).not.toBeNull());
    expect(patchBody!.beds?.double_size).toBe("super_king");
    useAuthStore.getState().clear();
  });

  it("hides the double-bed-size select when there is no double bed", async () => {
    setReservationsUser();
    const noDouble: PropertyRoom = {
      ...existingRoom,
      beds: { ...existingRoom.beds!, double: 0 },
    };
    renderWithProviders(
      <RoomFormDialog propertyId={7} open mode="edit" room={noDouble} onOpenChange={() => {}} />,
    );
    // Wait for the dialog to be interactive (Name field present) before asserting absence.
    await screen.findByLabelText(/^Name$/i);
    expect(screen.queryByRole("combobox", { name: /double bed size/i })).toBeNull();
    useAuthStore.getState().clear();
  });

  it("auto-checks Ensuite when a type is picked; unchecking Ensuite resets the type", async () => {
    setReservationsUser();
    renderWithProviders(
      <RoomFormDialog propertyId={7} open mode="create" onOpenChange={() => {}} />,
    );
    const ensuiteCheckbox = await screen.findByRole("checkbox", { name: /^ensuite$/i });
    expect(ensuiteCheckbox).not.toBeChecked();
    await choose(/ensuite type/i, /^bath$/i);
    expect(ensuiteCheckbox).toBeChecked();
    await userEvent.click(ensuiteCheckbox);
    expect(ensuiteCheckbox).not.toBeChecked();
    expect(screen.getByRole("combobox", { name: /ensuite type/i })).toHaveTextContent(/unknown/i);
    useAuthStore.getState().clear();
  });

  it("posts blank placement by default and submits a chosen floor (create, GAP-065)", async () => {
    setReservationsUser();
    let postedBody: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/properties/7/rooms", async ({ request }) => {
        postedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...existingRoom, id: 999, name: "New room" }, { status: 201 });
      }),
    );
    renderWithProviders(
      <RoomFormDialog propertyId={7} open mode="create" onOpenChange={() => {}} />,
    );
    // Both location selects start on their "not set" sentinel.
    expect(await screen.findByRole("combobox", { name: /placement/i })).toHaveTextContent(
      /not set/i,
    );
    expect(screen.getByRole("combobox", { name: /^floor$/i })).toHaveTextContent(/not set/i);
    await userEvent.type(screen.getByLabelText(/^Name$/i), "New room");
    await choose(/^floor$/i, /^first floor$/i);
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(postedBody).not.toBeNull());
    // No defaulted main_house lie — the user never picked a building.
    expect(postedBody).toMatchObject({ placement: "", floor: "first" });
    useAuthStore.getState().clear();
  });

  it("offers the new building members and clears placement to '' via the sentinel (edit, GAP-065)", async () => {
    setReservationsUser();
    let patchBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/properties/7/rooms/200", async ({ request }) => {
        patchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...existingRoom, placement: "" });
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
    // Edit path maps the stored value onto the trigger…
    const trigger = await screen.findByRole("combobox", { name: /placement/i });
    expect(trigger).toHaveTextContent(/main house/i);
    // …and the dropdown carries the GAP-065 members plus the sentinel.
    await userEvent.click(trigger);
    expect(screen.getByRole("option", { name: /^cottage$/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /^bungalow$/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /^studio$/i })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("option", { name: /^not set$/i }));
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(patchBody).not.toBeNull());
    expect(patchBody).toMatchObject({ placement: "" });
    useAuthStore.getState().clear();
  });

  it("shows the imported placement note in edit mode but never submits it (GAP-065)", async () => {
    setReservationsUser();
    const notedRoom: PropertyRoom = {
      ...existingRoom,
      placement: "guest_house",
      floor: "first",
      placement_note: "First floor of the guest house",
    };
    let patchBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/properties/7/rooms/200", async ({ request }) => {
        patchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(notedRoom);
      }),
    );
    renderWithProviders(
      <RoomFormDialog propertyId={7} open mode="edit" room={notedRoom} onOpenChange={() => {}} />,
    );
    expect(await screen.findByText(/First floor of the guest house/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(patchBody).not.toBeNull());
    expect(Object.keys(patchBody as unknown as Record<string, unknown>)).not.toContain(
      "placement_note",
    );
    // The stored axes still ride the payload untouched.
    expect(patchBody).toMatchObject({ placement: "guest_house", floor: "first" });
    useAuthStore.getState().clear();
  });

  it("hides the placement-note helper when the note is empty", async () => {
    setReservationsUser();
    renderWithProviders(
      <RoomFormDialog
        propertyId={7}
        open
        mode="edit"
        room={existingRoom}
        onOpenChange={() => {}}
      />,
    );
    await screen.findByLabelText(/^Name$/i);
    expect(screen.queryByText(/imported placement note/i)).not.toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("unticking an amenity removes it from the submitted full list (edit)", async () => {
    setReservationsUser();
    let patchBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/properties/7/rooms/200", async ({ request }) => {
        patchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(roomWithAmenities);
      }),
    );
    renderWithProviders(
      <RoomFormDialog
        propertyId={7}
        open
        mode="edit"
        room={roomWithAmenities}
        onOpenChange={() => {}}
      />,
    );
    const wardrobe = await screen.findByRole("checkbox", { name: /^wardrobe$/i });
    expect(wardrobe).toBeChecked();
    await userEvent.click(wardrobe);
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(patchBody).not.toBeNull());
    expect(patchBody).toMatchObject({ attribute_links: [{ attribute: 3, note: "" }] });
    useAuthStore.getState().clear();
  });

  it("keeps a retired-but-assigned amenity ticked, badged, and in the saved list (B1)", async () => {
    setReservationsUser();
    let patchBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/properties/7/rooms/200", async ({ request }) => {
        patchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(roomWithAmenities);
      }),
    );
    renderWithProviders(
      <RoomFormDialog
        propertyId={7}
        open
        mode="edit"
        room={roomWithAmenities}
        onOpenChange={() => {}}
      />,
    );
    const fireplace = await screen.findByRole("checkbox", { name: /^fireplace$/i });
    expect(fireplace).toBeChecked();
    // Styled as retired but NOT disabled — the user must still be able to untick.
    expect(fireplace).toBeEnabled();
    expect(screen.getByText(/^retired$/i)).toBeInTheDocument();
    // Save without touching the amenities: the retired link must survive.
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(patchBody).not.toBeNull());
    const links = (patchBody as unknown as { attribute_links: { attribute: number }[] })
      .attribute_links;
    expect(links).toContainEqual({ attribute: 3, note: "" });
    expect(links).toContainEqual({ attribute: 1, note: "walk-in" });
    useAuthStore.getState().clear();
  });
});
