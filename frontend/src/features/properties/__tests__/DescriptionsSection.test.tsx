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
    const textarea = (await screen.findByPlaceholderText(
      /Write the section content here/i,
    )) as HTMLTextAreaElement;
    await waitFor(() => expect(textarea.value).toBe("Welcome to Casa Sur."));
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
            { id: 2, property: 7, section: "location", body: "Ten minutes from Chania." },
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

    const textarea = (await screen.findByPlaceholderText(
      /Write the section content here/i,
    )) as HTMLTextAreaElement;
    await waitFor(() => expect(textarea.value).toBe("Welcome to Casa Sur."));

    await userEvent.click(screen.getByRole("button", { name: /^clear$/i }));
    const dialog = await screen.findByRole("dialog");
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
    await userEvent.click(await screen.findByRole("tab", { name: /house rules/i }));
    const textarea = await screen.findByPlaceholderText(/Write the section content here/i);
    await userEvent.type(textarea, "No smoking.");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(putBody).not.toBeNull());
    expect(putBody!.body).toBe("No smoking.");
    useAuthStore.getState().clear();
  });
});
