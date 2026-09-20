import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";
import { useAuthStore } from "@/features/auth/store";
import { DescriptionsSection } from "../components/DescriptionsSection";

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

const overviewRecord = {
  id: 1,
  property: 7,
  section: "overview",
  body: "Welcome to Casa Sur.",
  updated_at: "2026-05-01T00:00:00Z",
};

describe("DescriptionsSection", () => {
  it("loads existing overview body into the textarea", async () => {
    setReservationsUser();
    server.use(
      http.get("/api/v1/properties/7/descriptions", () =>
        HttpResponse.json(drfPage([overviewRecord])),
      ),
    );
    renderWithProviders(<DescriptionsSection propertyId={7} />);
    // GAP-090: the first tab is the Web description block, so Overview — a
    // single, unpaired section — is reached by its own tab.
    await userEvent.click(await screen.findByRole("tab", { name: "Overview" }));
    const textarea = screen.getByRole("textbox", { name: "Overview" }) as HTMLTextAreaElement;
    await waitFor(() => expect(textarea.value).toBe("Welcome to Casa Sur."));
    useAuthStore.getState().clear();
  });

  it("renders each block as a sub/para pair (GAP-090)", async () => {
    // The public site renders every website block as a short sub plus a longer
    // para, and legacy stores them as column pairs. Both halves must be
    // separately editable — they were fused into one section before GAP-090.
    setReservationsUser();
    server.use(
      http.get("/api/v1/properties/7/descriptions", () =>
        HttpResponse.json(
          drfPage([
            { id: 8, property: 7, section: "interior_sub", body: "Ensuite bedrooms." },
            { id: 9, property: 7, section: "interior_para", body: "Soft linen throughout." },
          ]),
        ),
      ),
    );
    renderWithProviders(<DescriptionsSection propertyId={7} />);

    await userEvent.click(await screen.findByRole("tab", { name: "Interior" }));
    await waitFor(() =>
      expect(
        (screen.getByRole("textbox", { name: "Interior sub" }) as HTMLTextAreaElement).value,
      ).toBe("Ensuite bedrooms."),
    );
    expect(
      (screen.getByRole("textbox", { name: "Interior para" }) as HTMLTextAreaElement).value,
    ).toBe("Soft linen throughout.");
    useAuthStore.getState().clear();
  });

  it("renders when the response carries sections the SPA doesn't know", async () => {
    // Regression: the schema pinned four sections while the backend had six, so
    // any imported property with `location`/`web_description` copy threw a
    // ZodError that React Query doesn't retry — collapsing the whole panel to
    // "Couldn't load descriptions". Unknown sections must degrade to
    // "not rendered", not take the known ones down with them (GAP-062).
    setReservationsUser();
    server.use(
      http.get("/api/v1/properties/7/descriptions", () =>
        HttpResponse.json(
          drfPage([
            overviewRecord,
            // `location` itself was retired by GAP-090; `location_sub` is the
            // live value this test needs as its *known* section.
            { id: 2, property: 7, section: "location_sub", body: "Ten minutes from Chania." },
            { id: 3, property: 7, section: "something_new", body: "From a newer backend." },
          ]),
        ),
      ),
    );
    renderWithProviders(<DescriptionsSection propertyId={7} />);
    expect(await screen.findByRole("tab", { name: /location/i })).toBeInTheDocument();
    expect(screen.queryByText(/Couldn't load descriptions/i)).not.toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("renders no villa_info tab and ignores other_information rows (GAP-091)", async () => {
    // `villa_info` left the backend enum and `other_information` moved to the
    // Features tab, so it is not a Descriptions-tab section and must not take
    // the panel down. `rooms` does render here now (GAP-092).
    setReservationsUser();
    server.use(
      http.get("/api/v1/properties/7/descriptions", () =>
        HttpResponse.json(
          drfPage([
            overviewRecord,
            { id: 5, property: 7, section: "other_information", body: "Pets on request." },
            { id: 6, property: 7, section: "rooms", body: "Five en-suite bedrooms." },
          ]),
        ),
      ),
    );
    renderWithProviders(<DescriptionsSection propertyId={7} />);
    await userEvent.click(await screen.findByRole("tab", { name: "Overview" }));
    await waitFor(() =>
      expect((screen.getByRole("textbox", { name: "Overview" }) as HTMLTextAreaElement).value).toBe(
        "Welcome to Casa Sur.",
      ),
    );

    expect(screen.queryByRole("tab", { name: "Villa information" })).not.toBeInTheDocument();
    // Four sub/para blocks plus the three unpaired sections.
    expect(screen.getAllByRole("tab")).toHaveLength(7);
    expect(screen.queryByDisplayValue("Pets on request.")).not.toBeInTheDocument();
    expect(screen.queryByText(/Couldn't load descriptions/i)).not.toBeInTheDocument();

    // The property-level rooms blurb is a section of its own now.
    await userEvent.click(screen.getByRole("tab", { name: "Rooms" }));
    expect((screen.getByRole("textbox", { name: "Rooms" }) as HTMLTextAreaElement).value).toBe(
      "Five en-suite bedrooms.",
    );
    useAuthStore.getState().clear();
  });

  it("keeps internal notes out of the website copy tabs and saves them separately", async () => {
    setReservationsUser();
    server.use(
      http.get("/api/v1/properties/7/descriptions", () =>
        HttpResponse.json(
          drfPage([
            { id: 4, property: 7, section: "internal_notes", body: "Owner prefers email." },
          ]),
        ),
      ),
    );
    let putBody: { body?: string } | null = null;
    server.use(
      http.put("/api/v1/properties/7/descriptions/internal-notes", async ({ request }) => {
        putBody = (await request.json()) as { body?: string };
        return HttpResponse.json({
          id: 4,
          property: 7,
          section: "internal_notes",
          body: putBody?.body ?? "",
        });
      }),
    );
    renderWithProviders(<DescriptionsSection propertyId={7} />);

    const notes = (await screen.findByPlaceholderText(
      /Not shown to guests/i,
    )) as HTMLTextAreaElement;
    await waitFor(() => expect(notes.value).toBe("Owner prefers email."));
    expect(screen.queryByRole("tab", { name: /internal notes/i })).not.toBeInTheDocument();

    await userEvent.type(notes, " Calls after 6pm.");
    await userEvent.click(screen.getByRole("button", { name: /save internal notes/i }));
    await waitFor(() => expect(putBody).not.toBeNull());
    expect(putBody!.body).toBe("Owner prefers email. Calls after 6pm.");
    useAuthStore.getState().clear();
  });

  it("empties the textarea after clearing a section", async () => {
    // The `seeded` ref blocks reseeding from refetches, so a successful delete
    // left the deleted copy sitting in the textarea — and re-enabled Save,
    // one click away from silently re-creating the section it just removed.
    setReservationsUser();
    server.use(
      http.get("/api/v1/properties/7/descriptions", () =>
        HttpResponse.json(drfPage([overviewRecord])),
      ),
      http.delete(
        "/api/v1/properties/7/descriptions/overview",
        () => new HttpResponse(null, { status: 204 }),
      ),
    );
    renderWithProviders(<DescriptionsSection propertyId={7} />);

    await userEvent.click(await screen.findByRole("tab", { name: "Overview" }));
    const textarea = screen.getByRole("textbox", { name: "Overview" }) as HTMLTextAreaElement;
    await waitFor(() => expect(textarea.value).toBe("Welcome to Casa Sur."));

    // Each button names its section: two editors share a block panel, and
    // Clear is a hard DELETE.
    await userEvent.click(screen.getByRole("button", { name: "Clear Overview" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Clear Overview?")).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: /^clear$/i }));

    await waitFor(() => expect(textarea.value).toBe(""));
    useAuthStore.getState().clear();
  });

  it("PUTs the upsert endpoint with hyphenated slug for house_rules", async () => {
    setReservationsUser();
    server.use(http.get("/api/v1/properties/7/descriptions", () => HttpResponse.json(drfPage([]))));
    let putBody: { body?: string } | null = null;
    server.use(
      http.put("/api/v1/properties/7/descriptions/house-rules", async ({ request }) => {
        putBody = (await request.json()) as { body?: string };
        return HttpResponse.json(
          { id: 2, property: 7, section: "house_rules", body: putBody?.body ?? "" },
          { status: 201 },
        );
      }),
    );
    renderWithProviders(<DescriptionsSection propertyId={7} />);
    await userEvent.click(await screen.findByRole("tab", { name: "House rules" }));
    const textarea = screen.getByRole("textbox", { name: "House rules" });
    await userEvent.type(textarea, "No smoking.");
    await userEvent.click(screen.getByRole("button", { name: "Save House rules" }));
    await waitFor(() => expect(putBody).not.toBeNull());
    expect(putBody!.body).toBe("No smoking.");
    useAuthStore.getState().clear();
  });
});
