import { http, HttpResponse } from "msw";
import { Navigate, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";
import { useAuthStore } from "@/features/auth/store";
import { PropertyDetailLayout } from "../PropertyDetailLayout";
import { FeaturesTab } from "../tabs/FeaturesTab";

const propertyFixture = {
  id: 7,
  name: "Casa Sur",
  display_name: "Casa Sur",
  slug: "casa-sur",
  licence_number: "ETV-7777",
  status: "active",
  channel: "direct",
  region: null,
  feature_ids: [11],
  legacy_id: null,
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2026-05-01T00:00:00Z",
};

const categories = [
  {
    id: 1,
    name: "Outdoor",
    slug: "outdoor",
    description: "",
    icon: "",
    sort_order: 1,
    is_active: true,
  },
  {
    id: 2,
    name: "Indoor",
    slug: "indoor",
    description: "",
    icon: "",
    sort_order: 2,
    is_active: true,
  },
  {
    id: 3,
    name: "Other information",
    slug: "other-information",
    description: "",
    icon: "",
    sort_order: 3,
    is_active: true,
  },
];

// GAP-091: "other information" tags are plain features in the
// `other-information` category — same catalogue, different section of the tab.
const otherInformationTags = [
  {
    id: 21,
    category: 3,
    name: "Pets allowed",
    slug: "pets-allowed",
    description: "",
    icon: "",
    sort_order: 1,
    is_active: true,
    service_type: "amenity",
  },
  {
    id: 22,
    category: 3,
    name: "Wheelchair access",
    slug: "wheelchair-access",
    description: "",
    icon: "",
    sort_order: 2,
    is_active: true,
    service_type: "amenity",
  },
  {
    id: 23,
    category: 3,
    name: "Staffed villa",
    slug: "staffed-villa",
    description: "",
    icon: "",
    sort_order: 3,
    is_active: true,
    service_type: "amenity",
  },
];

const features = [
  {
    id: 11,
    category: 1,
    name: "Pool",
    slug: "pool",
    description: "",
    icon: "",
    sort_order: 1,
    is_active: true,
    service_type: "amenity",
  },
  {
    id: 12,
    category: 1,
    name: "BBQ",
    slug: "bbq",
    description: "",
    icon: "",
    sort_order: 2,
    is_active: true,
    service_type: "amenity",
  },
  {
    id: 13,
    category: 2,
    name: "Wi-Fi",
    slug: "wifi",
    description: "",
    icon: "",
    sort_order: 1,
    is_active: true,
    service_type: "amenity",
  },
];

function installBaseHandlers({ inactiveTagIds = [] }: { inactiveTagIds?: number[] } = {}) {
  const tags = otherInformationTags.map((tag) =>
    inactiveTagIds.includes(tag.id) ? { ...tag, is_active: false } : tag,
  );
  server.use(
    http.get("/api/v1/properties/casa-sur", () => HttpResponse.json(propertyFixture)),
    http.get("/api/v1/features", () => HttpResponse.json(drfPage([...features, ...tags]))),
    http.get("/api/v1/feature-categories", () => HttpResponse.json(drfPage(categories))),
    http.get("/api/v1/properties/7/descriptions", () => HttpResponse.json(drfPage([]))),
  );
}

function installProperty(overrides: Partial<typeof propertyFixture> & Record<string, unknown>) {
  server.use(
    http.get("/api/v1/properties/casa-sur", () =>
      HttpResponse.json({ ...propertyFixture, ...overrides }),
    ),
  );
}

function capturePatch() {
  const captured: { body: { features?: number[] } | null } = { body: null };
  server.use(
    http.patch("/api/v1/properties/7", async ({ request }) => {
      captured.body = (await request.json()) as { features?: number[] };
      return HttpResponse.json({ ...propertyFixture, feature_ids: captured.body.features ?? [] });
    }),
  );
  return captured;
}

function otherInformationSection() {
  return screen.getByTestId("other-information-section");
}

/** Ids of the sortable rows rendered inside `container`, in DOM order. */
function rowIdsWithin(container: HTMLElement) {
  return within(container)
    .getAllByTestId(/^property-feature-row-/)
    .map((el) => Number(el.dataset.testid?.replace("property-feature-row-", "")));
}

/** Ids of the sortable rows rendered OUTSIDE the other-information section. */
function mainRowIds() {
  const section = otherInformationSection();
  return screen
    .getAllByTestId(/^property-feature-row-/)
    .filter((el) => !section.contains(el))
    .map((el) => Number(el.dataset.testid?.replace("property-feature-row-", "")));
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

function setup() {
  return renderWithProviders(
    <Routes>
      <Route path="/properties/:id" element={<PropertyDetailLayout />}>
        <Route index element={<Navigate to="features" replace />} />
        <Route path="features" element={<FeaturesTab />} />
      </Route>
    </Routes>,
    { route: "/properties/casa-sur/features" },
  );
}

function featureRow(id: number) {
  return screen.getByTestId(`property-feature-row-${id}`);
}

afterEach(() => {
  useAuthStore.getState().clear();
});

describe("FeaturesTab", () => {
  it("renders the selected features as an ordered list; unselected stay out of it", async () => {
    setReservationsUser();
    installBaseHandlers();
    setup();
    await waitFor(() => expect(featureRow(11)).toBeInTheDocument());
    expect(within(featureRow(11)).getByText("Pool")).toBeInTheDocument();
    // BBQ / Wi-Fi are unselected — not rendered as rows.
    expect(screen.queryByTestId("property-feature-row-12")).not.toBeInTheDocument();
    expect(screen.queryByTestId("property-feature-row-13")).not.toBeInTheDocument();
  });

  it("disables Save until the selection changes, then adds a feature via the Add menu", async () => {
    setReservationsUser();
    installBaseHandlers();
    setup();
    const save = await screen.findByRole("button", { name: /save changes/i });
    expect(save).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: /add feature/i }));
    await userEvent.click(await screen.findByRole("menuitem", { name: /bbq/i }));

    expect(featureRow(12)).toBeInTheDocument();
    expect(save).toBeEnabled();
  });

  it("PATCHes /properties/{id} with the features in LIST ORDER (not sorted)", async () => {
    setReservationsUser();
    installBaseHandlers();
    // Start with Wi-Fi(13) before Pool(11) so a naive sort would reorder them;
    // the payload must preserve list order — the GAP-022 sort_order contract.
    server.use(
      http.get("/api/v1/properties/casa-sur", () =>
        HttpResponse.json({ ...propertyFixture, feature_ids: [13, 11] }),
      ),
    );
    let patchedBody: { features?: number[] } | null = null;
    server.use(
      http.patch("/api/v1/properties/7", async ({ request }) => {
        patchedBody = (await request.json()) as { features?: number[] };
        return HttpResponse.json({ ...propertyFixture, feature_ids: patchedBody?.features ?? [] });
      }),
    );
    setup();

    // Append BBQ(12) last — it must land at the end of the ordered payload.
    await userEvent.click(await screen.findByRole("button", { name: /add feature/i }));
    await userEvent.click(await screen.findByRole("menuitem", { name: /bbq/i }));
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => expect(patchedBody).not.toBeNull());
    expect(patchedBody!.features).toEqual([13, 11, 12]);
  });

  it("removes a feature from the selection", async () => {
    setReservationsUser();
    installBaseHandlers();
    let patchedBody: { features?: number[] } | null = null;
    server.use(
      http.patch("/api/v1/properties/7", async ({ request }) => {
        patchedBody = (await request.json()) as { features?: number[] };
        return HttpResponse.json({ ...propertyFixture, feature_ids: patchedBody?.features ?? [] });
      }),
    );
    setup();
    await userEvent.click(await screen.findByRole("button", { name: /remove pool/i }));
    expect(screen.queryByTestId("property-feature-row-11")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));
    await waitFor(() => expect(patchedBody).not.toBeNull());
    expect(patchedBody!.features).toEqual([]);
  });

  it("shows derived features as read-only chips, out of the sortable list and save payload (GAP-067)", async () => {
    setReservationsUser();
    installBaseHandlers();
    // Wi-Fi(13) is derived from a room attribute; Pool(11) is manual.
    let patchedBody: { features?: number[] } | null = null;
    server.use(
      http.get("/api/v1/properties/casa-sur", () =>
        HttpResponse.json({ ...propertyFixture, feature_ids: [11, 13], derived_feature_ids: [13] }),
      ),
      http.patch("/api/v1/properties/7", async ({ request }) => {
        patchedBody = (await request.json()) as { features?: number[] };
        return HttpResponse.json({ ...propertyFixture, feature_ids: patchedBody?.features ?? [] });
      }),
    );
    setup();

    // Pool(11) is an editable sortable row; Wi-Fi(13) is NOT in the sortable list.
    await waitFor(() => expect(featureRow(11)).toBeInTheDocument());
    expect(screen.queryByTestId("property-feature-row-13")).not.toBeInTheDocument();

    // Wi-Fi(13) renders as a read-only derived chip with no remove control.
    const chip = screen.getByTestId("property-derived-feature-13");
    expect(within(chip).getByText("Wi-Fi")).toBeInTheDocument();
    expect(within(chip).queryByRole("button")).not.toBeInTheDocument();

    // Filtering the derived id out must NOT make the tab look dirty.
    const save = screen.getByRole("button", { name: /save changes/i });
    expect(save).toBeDisabled();

    // A derived feature is not offered again in the Add menu.
    await userEvent.click(screen.getByRole("button", { name: /add feature/i }));
    expect(screen.queryByRole("menuitem", { name: /wi-fi/i })).not.toBeInTheDocument();
    await userEvent.click(await screen.findByRole("menuitem", { name: /bbq/i }));

    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));
    await waitFor(() => expect(patchedBody).not.toBeNull());
    // Manual-only payload: derived id 13 is excluded.
    expect(patchedBody!.features).toEqual([11, 12]);
  });

  it("reverts local edits on Reset", async () => {
    setReservationsUser();
    installBaseHandlers();
    setup();
    await userEvent.click(await screen.findByRole("button", { name: /add feature/i }));
    await userEvent.click(await screen.findByRole("menuitem", { name: /bbq/i }));
    expect(featureRow(12)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /reset/i }));
    expect(screen.queryByTestId("property-feature-row-12")).not.toBeInTheDocument();
  });

  describe("Other information section (GAP-091)", () => {
    it("renders other-information tags in the section in property order, not in the main list", async () => {
      setReservationsUser();
      installBaseHandlers();
      // Interleaved on purpose: the legacy loader can leave tag ids and main
      // ids mixed in the persisted order.
      installProperty({ feature_ids: [22, 11, 21] });
      setup();
      await waitFor(() => expect(featureRow(11)).toBeInTheDocument());

      expect(rowIdsWithin(otherInformationSection())).toEqual([22, 21]);
      expect(mainRowIds()).toEqual([11]);
      expect(within(otherInformationSection()).getByText("Wheelchair access")).toBeInTheDocument();
    });

    it("keeps tags out of the main Add menu and offers ONLY tags in the section's Add menu", async () => {
      setReservationsUser();
      installBaseHandlers();
      setup();
      await waitFor(() => expect(featureRow(11)).toBeInTheDocument());

      await userEvent.click(screen.getByRole("button", { name: /add feature/i }));
      expect(await screen.findByRole("menuitem", { name: /bbq/i })).toBeInTheDocument();
      expect(screen.queryByRole("menuitem", { name: /pets allowed/i })).not.toBeInTheDocument();
      await userEvent.keyboard("{Escape}");
      await waitFor(() =>
        expect(screen.queryByRole("menuitem", { name: /bbq/i })).not.toBeInTheDocument(),
      );

      await userEvent.click(screen.getByRole("button", { name: /add tag/i }));
      expect(await screen.findByRole("menuitem", { name: /pets allowed/i })).toBeInTheDocument();
      expect(screen.getByRole("menuitem", { name: /wheelchair access/i })).toBeInTheDocument();
      expect(screen.queryByRole("menuitem", { name: /bbq/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("menuitem", { name: /wi-fi/i })).not.toBeInTheDocument();
    });

    it("is not dirty on mount with an interleaved order; adding a tag appends to the saved order", async () => {
      setReservationsUser();
      installBaseHandlers();
      installProperty({ feature_ids: [21, 11, 22] });
      const patched = capturePatch();
      setup();
      await waitFor(() => expect(featureRow(11)).toBeInTheDocument());

      // Splitting the interleaved order into two views must NOT look like an edit.
      const save = screen.getByRole("button", { name: /save changes/i });
      expect(save).toBeDisabled();

      await userEvent.click(screen.getByRole("button", { name: /add tag/i }));
      await userEvent.click(await screen.findByRole("menuitem", { name: /staffed villa/i }));
      expect(rowIdsWithin(otherInformationSection())).toEqual([21, 22, 23]);
      expect(save).toBeEnabled();

      await userEvent.click(save);
      await waitFor(() => expect(patched.body).not.toBeNull());
      // The interleaved order is kept verbatim; the new tag appends.
      expect(patched.body!.features).toEqual([21, 11, 22, 23]);
    });

    it("stays clean after a net-zero add then remove on an interleaved order", async () => {
      setReservationsUser();
      installBaseHandlers();
      installProperty({ feature_ids: [21, 11, 22] });
      setup();
      await waitFor(() => expect(featureRow(11)).toBeInTheDocument());
      const save = screen.getByRole("button", { name: /save changes/i });

      await userEvent.click(screen.getByRole("button", { name: /add tag/i }));
      await userEvent.click(await screen.findByRole("menuitem", { name: /staffed villa/i }));
      expect(save).toBeEnabled();
      await userEvent.click(within(featureRow(23)).getByRole("button", { name: /^remove/i }));

      expect(rowIdsWithin(otherInformationSection())).toEqual([21, 22]);
      expect(save).toBeDisabled();
    });

    it("keeps a selected tag visible and removable after its feature is deactivated", async () => {
      setReservationsUser();
      installBaseHandlers({ inactiveTagIds: [21, 22, 23] });
      installProperty({ feature_ids: [11, 21] });
      setup();
      await waitFor(() => expect(featureRow(11)).toBeInTheDocument());

      expect(rowIdsWithin(otherInformationSection())).toEqual([21]);
      expect(screen.queryByText(/no other-information tags available/i)).not.toBeInTheDocument();
      expect(within(featureRow(21)).getByRole("button", { name: /^remove/i })).toBeInTheDocument();
    });

    it("removes a tag from the section and drops it from the PATCH body", async () => {
      setReservationsUser();
      installBaseHandlers();
      installProperty({ feature_ids: [21, 11, 22] });
      const patched = capturePatch();
      setup();
      await waitFor(() => expect(featureRow(21)).toBeInTheDocument());
      expect(rowIdsWithin(otherInformationSection())).toEqual([21, 22]);

      await userEvent.click(screen.getByRole("button", { name: /remove pets allowed/i }));
      expect(screen.queryByTestId("property-feature-row-21")).not.toBeInTheDocument();
      expect(featureRow(11)).toBeInTheDocument();

      await userEvent.click(screen.getByRole("button", { name: /save changes/i }));
      await waitFor(() => expect(patched.body).not.toBeNull());
      expect(patched.body!.features).toEqual([11, 22]);
    });

    it("renders a derived other-information feature as a chip inside the section, not among the main chips", async () => {
      setReservationsUser();
      installBaseHandlers();
      installProperty({ feature_ids: [11, 21, 22], derived_feature_ids: [22] });
      const patched = capturePatch();
      setup();
      await waitFor(() => expect(featureRow(11)).toBeInTheDocument());

      const chip = screen.getByTestId("property-derived-feature-22");
      expect(otherInformationSection()).toContainElement(chip);
      expect(within(chip).getByText("Wheelchair access")).toBeInTheDocument();
      expect(within(chip).queryByRole("button")).not.toBeInTheDocument();
      // No main-list derived block: the only derived feature is a tag.
      expect(screen.queryByRole("heading", { name: /from rooms/i })).not.toBeInTheDocument();
      expect(screen.queryByTestId("property-feature-row-22")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: /save changes/i })).toBeDisabled();

      // Not re-offered in the section's Add menu; not in the payload either.
      await userEvent.click(screen.getByRole("button", { name: /add tag/i }));
      expect(
        screen.queryByRole("menuitem", { name: /wheelchair access/i }),
      ).not.toBeInTheDocument();
      await userEvent.click(await screen.findByRole("menuitem", { name: /staffed villa/i }));
      await userEvent.click(screen.getByRole("button", { name: /save changes/i }));
      await waitFor(() => expect(patched.body).not.toBeNull());
      expect(patched.body!.features).toEqual([11, 21, 23]);
    });

    it("loads, saves and clears the other-information description through its own endpoint", async () => {
      setReservationsUser();
      installBaseHandlers();
      let putBody: { body?: string } | null = null;
      let deleted = false;
      // Stateful like the server: the refetch after Save echoes the saved body,
      // which is what settles the Save/Clear enablement.
      let stored = "Pets on request.";
      server.use(
        http.get("/api/v1/properties/7/descriptions", () =>
          HttpResponse.json(
            drfPage([
              { id: 9, property: 7, section: "other_information", body: stored },
              { id: 10, property: 7, section: "overview", body: "Not this one." },
            ]),
          ),
        ),
        http.put("/api/v1/properties/7/descriptions/other-information", async ({ request }) => {
          putBody = (await request.json()) as { body?: string };
          stored = putBody?.body ?? "";
          return HttpResponse.json({
            id: 9,
            property: 7,
            section: "other_information",
            body: stored,
          });
        }),
        http.delete("/api/v1/properties/7/descriptions/other-information", () => {
          deleted = true;
          return new HttpResponse(null, { status: 204 });
        }),
      );
      setup();

      const textarea = (await screen.findByLabelText(
        /other information description/i,
      )) as HTMLTextAreaElement;
      await waitFor(() => expect(textarea.value).toBe("Pets on request."));
      const saveDescription = screen.getByRole("button", { name: /save description/i });
      expect(saveDescription).toBeDisabled();

      await userEvent.type(textarea, " Ask first.");
      expect(saveDescription).toBeEnabled();
      await userEvent.click(saveDescription);
      await waitFor(() => expect(putBody).not.toBeNull());
      expect(putBody!.body).toBe("Pets on request. Ask first.");

      await userEvent.click(screen.getByRole("button", { name: /clear description/i }));
      const dialog = await screen.findByRole("dialog");
      await userEvent.click(within(dialog).getByRole("button", { name: /^clear$/i }));
      await waitFor(() => expect(deleted).toBe(true));
      await waitFor(() => expect(textarea.value).toBe(""));
    });

    it("shows an empty state pointing at the Tags admin when there is no other-information vocabulary", async () => {
      setReservationsUser();
      installBaseHandlers();
      server.use(
        http.get("/api/v1/features", () => HttpResponse.json(drfPage(features))),
        http.get("/api/v1/feature-categories", () =>
          HttpResponse.json(drfPage(categories.filter((c) => c.slug !== "other-information"))),
        ),
      );
      setup();
      await waitFor(() => expect(featureRow(11)).toBeInTheDocument());

      expect(
        within(otherInformationSection()).getByText(/managed in the tags admin/i),
      ).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /add tag/i })).not.toBeInTheDocument();
      // The description box does not depend on the vocabulary.
      expect(await screen.findByLabelText(/other information description/i)).toBeInTheDocument();
    });
  });
});
