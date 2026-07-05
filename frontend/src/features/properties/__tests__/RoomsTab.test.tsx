import { http, HttpResponse } from "msw";
import { Navigate, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { DragEndEvent } from "@dnd-kit/core";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";
import { useAuthStore } from "@/features/auth/store";
import { PropertyDetailLayout } from "../PropertyDetailLayout";
import { RoomsTab } from "../tabs/RoomsTab";

// jsdom can't drive a real dnd-kit pointer drag (no layout), so wrap the real
// DndContext to capture each context's onDragEnd, keyed by the `id` the
// component assigns ("rooms-flat" / "rooms-group-<placement>|<floor>"). Tests
// fire the captured handler with a synthetic DragEndEvent — everything from
// the drop handler down (arrayMove, re-flatten, POST) is real code.
const dndHandlers = vi.hoisted(
  () => ({}) as Record<string, (event: DragEndEvent) => void | Promise<void>>,
);
vi.mock("@dnd-kit/core", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@dnd-kit/core")>();
  const { createElement } = await import("react");
  type DndContextProps = Parameters<typeof actual.DndContext>[0];
  return {
    ...actual,
    DndContext: (props: DndContextProps) => {
      if (props.id && props.onDragEnd) dndHandlers[props.id] = props.onDragEnd;
      return createElement(actual.DndContext, props);
    },
  };
});

beforeEach(() => {
  // Clear the captured handlers so a stale closure over a previous test's
  // unmounted component can never satisfy a later toBeDefined().
  for (const key of Object.keys(dndHandlers)) delete dndHandlers[key];
});

const propertyFixture = {
  id: 7,
  name: "Casa Sur",
  display_name: "Casa Sur",
  slug: "casa-sur",
  licence_number: "ETV-7777",
  status: "active",
  channel: "direct",
  category: null,
  group: null,
  region: null,
  feature_ids: [],
  legacy_id: null,
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2026-05-01T00:00:00Z",
};

const roomA = {
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

const roomB = {
  id: 201,
  property: 7,
  name: "Twin room",
  placement: "main_house",
  website_description: "",
  vc_notes: "",
  is_ensuite: false,
  sort_order: 1,
  beds: {
    double: 0,
    twin_double: 0,
    twin: 2,
    single: 0,
    bunk: 0,
    sofa: 0,
    childrens: 0,
  },
};

function installBaseHandlers() {
  server.use(http.get("/api/v1/properties/casa-sur", () => HttpResponse.json(propertyFixture)));
}

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

function setReadonlyUser() {
  useAuthStore.getState().setMe(
    {
      id: 2,
      email: "r@test.com",
      first_name: "R",
      last_name: "T",
      is_active: true,
      is_staff: false,
      is_superuser: false,
      preferred_language: "en",
      role: "READONLY",
    },
    { role: "READONLY", is_superuser: false, permissions: [] },
  );
}

function setup() {
  return renderWithProviders(
    <Routes>
      <Route path="/properties/:id" element={<PropertyDetailLayout />}>
        <Route index element={<Navigate to="rooms" replace />} />
        <Route path="rooms" element={<RoomsTab />} />
      </Route>
    </Routes>,
    { route: "/properties/casa-sur/rooms" },
  );
}

// GAP-064: facets + assigned amenities (attribute_links read shape).
const roomC = {
  ...roomA,
  id: 202,
  name: "Garden suite",
  is_ensuite: true,
  ensuite_type: "shower",
  access: "outside",
  sort_order: 2,
  attribute_links: [
    {
      id: 90,
      attribute: 1,
      slug: "wardrobe",
      name: "Wardrobe",
      icon: "shirt",
      is_active: true,
      note: "",
    },
    {
      id: 91,
      attribute: 3,
      slug: "fireplace",
      name: "Fireplace",
      icon: "flame",
      is_active: false,
      note: "gas",
    },
  ],
};

// GAP-065 location fixtures. Server order is deliberately interleaved so the
// grouped tests prove ordering comes from the (placement, floor) axes, and the
// reorder test proves the re-flatten follows group display order.
const roomGround = { ...roomA, floor: "ground" };
const roomGuestFirst = { ...roomB, placement: "guest_house", floor: "first" };
const roomStudy = { ...roomA, id: 205, name: "Study", sort_order: 2, floor: "ground" };
const roomNowhere = {
  ...roomB,
  id: 206,
  name: "Cellar den",
  placement: "",
  floor: "",
  sort_order: 3,
};

describe("RoomsTab", () => {
  it("renders a single-group list flat, with placement badges and bed summary (B1)", async () => {
    // Both rooms share (main_house, blank floor) — one distinct group key, so
    // no headers sprout; the placement rides each row as a badge instead.
    setReservationsUser();
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/7/rooms", () => HttpResponse.json(drfPage([roomA, roomB]))),
    );
    setup();
    await waitFor(() => expect(screen.getByText("Master bedroom")).toBeInTheDocument());
    expect(screen.getByText("Twin room")).toBeInTheDocument();
    expect(screen.getAllByText("Main house")).toHaveLength(2);
    expect(screen.queryByRole("heading", { name: /main house/i })).not.toBeInTheDocument();
    expect(screen.getByText(/1 double/i)).toBeInTheDocument();
    expect(screen.getByText(/2 twins/i)).toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("renders amenity chips and facet badges for a room with attribute_links (GAP-064)", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(http.get("/api/v1/properties/7/rooms", () => HttpResponse.json(drfPage([roomC]))));
    setup();
    await waitFor(() => expect(screen.getByText("Garden suite")).toBeInTheDocument());
    // Amenity chips render name (icon is decorative) — retired links included.
    expect(screen.getByText("Wardrobe")).toBeInTheDocument();
    expect(screen.getByText("Fireplace")).toBeInTheDocument();
    // Ensuite badge carries the type; access surfaces as its own badge.
    expect(screen.getByText(/Ensuite · Shower/i)).toBeInTheDocument();
    expect(screen.getByText(/^Outside$/i)).toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("shows a floor badge on flat rows when the shared key has a floor (GAP-065)", async () => {
    // One distinct (main_house, ground) key → flat list, so no header exists
    // to say the floor; each row must carry it as a badge alongside placement.
    setReservationsUser();
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/7/rooms", () =>
        HttpResponse.json(drfPage([roomGround, roomStudy])),
      ),
    );
    setup();
    await waitFor(() => expect(screen.getByText("Study")).toBeInTheDocument());
    expect(screen.queryByRole("heading", { level: 3 })).not.toBeInTheDocument();
    expect(screen.getAllByText("Main house")).toHaveLength(2);
    expect(screen.getAllByText("Ground floor")).toHaveLength(2);
    useAuthStore.getState().clear();
  });

  it("groups rooms under building · floor headers when keys differ (GAP-065)", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/7/rooms", () =>
        HttpResponse.json(drfPage([roomNowhere, roomGuestFirst, roomGround])),
      ),
    );
    setup();
    await waitFor(() => expect(screen.getByText("Master bedroom")).toBeInTheDocument());
    // Building order follows the ROOM_PLACEMENTS tuple; the all-blank group
    // sorts last under its own label.
    const headings = screen.getAllByRole("heading", { level: 3 });
    expect(headings.map((h) => h.textContent)).toEqual([
      "Main house · Ground floor",
      "Guest house · First floor",
      "No location set",
    ]);
    // Each row sits under its own header…
    within(screen.getByRole("region", { name: "Main house · Ground floor" })).getByText(
      "Master bedroom",
    );
    within(screen.getByRole("region", { name: "Guest house · First floor" })).getByText(
      "Twin room",
    );
    within(screen.getByRole("region", { name: "No location set" })).getByText("Cellar den");
    // …and rows carry no placement badge (the header already says it): the only
    // "Main house" text on screen is the header itself.
    expect(screen.getAllByText(/Main house/)).toHaveLength(1);
    // The blank-placement row must not leak a raw i18n key as badge text.
    expect(screen.queryByText(/rooms\.placements\./)).not.toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("renders a lone blank-location room flat with no badge and no broken key text", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/7/rooms", () => HttpResponse.json(drfPage([roomNowhere]))),
    );
    setup();
    await waitFor(() => expect(screen.getByText("Cellar den")).toBeInTheDocument());
    expect(screen.queryByRole("heading", { level: 3 })).not.toBeInTheDocument();
    expect(screen.queryByText(/rooms\.placements\./)).not.toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("posts the full flattened id order after a within-group drag (GAP-065)", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(
      http.get("/api/v1/properties/7/rooms", () =>
        HttpResponse.json(drfPage([roomGround, roomGuestFirst, roomStudy, roomNowhere])),
      ),
    );
    let reorderBody: unknown = null;
    server.use(
      http.post("/api/v1/properties/7/rooms:reorder", async ({ request }) => {
        reorderBody = await request.json();
        return new HttpResponse(null, { status: 204 });
      }),
    );
    setup();
    await waitFor(() => expect(screen.getByText("Study")).toBeInTheDocument());
    // Groups render as: Main house·Ground [200, 205] / Guest house·First [201]
    // / unassigned [206]. Drop Master bedroom (200) onto Study (205) within
    // the first group.
    const handler = dndHandlers["rooms-group-main_house|ground"];
    expect(handler).toBeDefined();
    await act(async () => {
      await handler({ active: { id: 200 }, over: { id: 205 } } as DragEndEvent);
    });
    // The whole property's rooms are re-flattened in group display order — not
    // just the dragged group's slice.
    await waitFor(() => expect(reorderBody).toEqual({ room_ids: [205, 200, 201, 206] }));
    useAuthStore.getState().clear();
  });

  it("shows empty state when there are no rooms", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(http.get("/api/v1/properties/7/rooms", () => HttpResponse.json(drfPage([]))));
    setup();
    expect(await screen.findByText(/No rooms yet/i)).toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("disables Add room when the user lacks the RESERVATIONS role", async () => {
    setReadonlyUser();
    installBaseHandlers();
    server.use(http.get("/api/v1/properties/7/rooms", () => HttpResponse.json(drfPage([]))));
    setup();
    const btn = await screen.findByRole("button", { name: /add room/i });
    expect(btn).toBeDisabled();
    useAuthStore.getState().clear();
  });

  it("opens the Add room dialog when role allows", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(http.get("/api/v1/properties/7/rooms", () => HttpResponse.json(drfPage([]))));
    setup();
    const btn = await screen.findByRole("button", { name: /add room/i });
    expect(btn).toBeEnabled();
    await userEvent.click(btn);
    expect(await screen.findByLabelText(/^Name$/i)).toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("deletes a room via the menu and confirm dialog", async () => {
    setReservationsUser();
    installBaseHandlers();
    server.use(http.get("/api/v1/properties/7/rooms", () => HttpResponse.json(drfPage([roomA]))));
    let deleteCalled = false;
    server.use(
      http.delete("/api/v1/properties/7/rooms/200", () => {
        deleteCalled = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    setup();
    await waitFor(() => expect(screen.getByText("Master bedroom")).toBeInTheDocument());
    const menu = await screen.findByRole("button", { name: /actions/i });
    await userEvent.click(menu);
    const deleteItem = await screen.findByText(/^Delete$/i);
    await userEvent.click(deleteItem);
    const confirm = await screen.findByRole("button", { name: /^Remove$/i });
    await userEvent.click(confirm);
    await waitFor(() => expect(deleteCalled).toBe(true));
    useAuthStore.getState().clear();
  });
});
