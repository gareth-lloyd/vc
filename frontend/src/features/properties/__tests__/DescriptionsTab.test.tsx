import { http, HttpResponse } from "msw";
import { Navigate } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithDataRouter } from "@/test/render";
import { drfPage } from "@/test/drf";
import { precedes } from "@/test/dom";
import { useAuthStore } from "@/features/auth/store";
import { PropertyDetailLayout } from "../PropertyDetailLayout";
import { DescriptionsTab } from "../tabs/DescriptionsTab";

const propertyFixture = {
  id: 7,
  name: "Casa Sur",
  display_name: "Casa Sur",
  slug: "casa-sur",
  licence_number: "ETV-7777",
  status: "active",
  channel: "direct",
  region: null,
  feature_ids: [],
  video_url: "https://video.example/casa-sur",
  legacy_id: null,
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2026-05-01T00:00:00Z",
};

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

function installBaseHandlers(property: Record<string, unknown> = propertyFixture) {
  server.use(
    http.get("/api/v1/properties/casa-sur", () => HttpResponse.json(property)),
    http.get("/api/v1/properties/7/descriptions", () =>
      HttpResponse.json(
        drfPage([{ id: 1, property: 7, section: "web_des_1", body: "A villa above the bay." }]),
      ),
    ),
  );
}

// Data router (not MemoryRouter): the tab mounts `useUnsavedChangesGuard` →
// `useBlocker`, which requires one. `details` is the guard's navigation target.
function setup() {
  return renderWithDataRouter(
    [
      {
        path: "/properties/:id",
        element: <PropertyDetailLayout />,
        children: [
          { index: true, element: <Navigate to="descriptions" replace /> },
          { path: "descriptions", element: <DescriptionsTab /> },
          { path: "details", element: <div>details-stub</div> },
        ],
      },
    ],
    { route: "/properties/casa-sur/descriptions" },
  );
}

const detailsTab = () => screen.getByRole("link", { name: "Details" });

afterEach(() => {
  cleanup();
  useAuthStore.getState().clear();
});

describe("DescriptionsTab (GAP-090)", () => {
  it("renders the copy sections, then the video URL, then internal notes", async () => {
    setReservationsUser();
    installBaseHandlers();
    setup();

    const sub = (await screen.findByRole("textbox", { name: "Web des 1" })) as HTMLTextAreaElement;
    await waitFor(() => expect(sub.value).toBe("A villa above the bay."));
    expect(screen.getByRole("textbox", { name: "Web des 2" })).toBeInTheDocument();
    const video = screen.getByLabelText("Video URL") as HTMLInputElement;
    expect(video.value).toBe("https://video.example/casa-sur");

    // One column in website order; the video editor sits after the last
    // website section and before the staff-only notes.
    expect(precedes(screen.getByRole("textbox", { name: "House rules" }), video)).toBe(true);
    expect(precedes(video, screen.getByRole("textbox", { name: "Internal notes" }))).toBe(true);
  });

  describe("Unsaved changes guard (GAP-083)", () => {
    it("blocks a tab change while a description draft is unsaved; Stay keeps it", async () => {
      setReservationsUser();
      installBaseHandlers();
      const { router } = setup();

      const sub = await screen.findByRole("textbox", { name: "Web des 1" });
      await waitFor(() => expect((sub as HTMLTextAreaElement).value).not.toBe(""));
      expect(screen.queryByText("Unsaved changes")).not.toBeInTheDocument();
      await userEvent.type(sub, " Sleeps ten.");
      expect(screen.getByText("Unsaved changes")).toBeInTheDocument();

      await userEvent.click(detailsTab());
      const dialog = await screen.findByRole("dialog", { name: "Discard unsaved changes?" });
      await userEvent.click(within(dialog).getByRole("button", { name: "Stay" }));

      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
      expect(router.state.location.pathname).toBe("/properties/casa-sur/descriptions");
      expect((sub as HTMLTextAreaElement).value).toBe("A villa above the bay. Sleeps ten.");
    });

    it("stops guarding once the draft is saved", async () => {
      setReservationsUser();
      installBaseHandlers();
      let saved = "A villa above the bay.";
      server.use(
        http.get("/api/v1/properties/7/descriptions", () =>
          HttpResponse.json(drfPage([{ id: 1, property: 7, section: "web_des_1", body: saved }])),
        ),
        http.put("/api/v1/properties/7/descriptions/web-des-1", async ({ request }) => {
          saved = ((await request.json()) as { body: string }).body;
          return HttpResponse.json({ id: 1, property: 7, section: "web_des_1", body: saved });
        }),
      );
      const { router } = setup();

      const sub = await screen.findByRole("textbox", { name: "Web des 1" });
      await waitFor(() => expect((sub as HTMLTextAreaElement).value).not.toBe(""));
      await userEvent.type(sub, " Sleeps ten.");
      await userEvent.click(screen.getByRole("button", { name: "Save Web des 1" }));
      await waitFor(() => expect(screen.queryByText("Unsaved changes")).not.toBeInTheDocument());

      await userEvent.click(detailsTab());
      expect(await screen.findByText("details-stub")).toBeInTheDocument();
      expect(router.state.location.pathname).toBe("/properties/casa-sur/details");
    });

    it("guards an unsaved video URL too, and Reset drops every draft", async () => {
      setReservationsUser();
      installBaseHandlers();
      setup();

      const sub = await screen.findByRole("textbox", { name: "Web des 1" });
      await waitFor(() => expect((sub as HTMLTextAreaElement).value).not.toBe(""));
      const video = screen.getByLabelText("Video URL") as HTMLInputElement;
      await userEvent.type(video, "/tour");
      expect(screen.getByText("Unsaved changes")).toBeInTheDocument();

      await userEvent.click(detailsTab());
      const dialog = await screen.findByRole("dialog", { name: "Discard unsaved changes?" });
      await userEvent.click(within(dialog).getByRole("button", { name: "Stay" }));

      await userEvent.type(screen.getByRole("textbox", { name: "Web des 1" }), " Draft.");
      await userEvent.click(screen.getByRole("button", { name: "Reset" }));
      await waitFor(() => expect(screen.queryByText("Unsaved changes")).not.toBeInTheDocument());
      expect((screen.getByLabelText("Video URL") as HTMLInputElement).value).toBe(
        "https://video.example/casa-sur",
      );
      expect(
        (screen.getByRole("textbox", { name: "Web des 1" }) as HTMLTextAreaElement).value,
      ).toBe("A villa above the bay.");
    });

    it("keeps guarding a draft while another section's clear is in flight", async () => {
      setReservationsUser();
      installBaseHandlers();
      let release: () => void = () => {};
      const held = new Promise<void>((resolve) => (release = resolve));
      server.use(
        http.delete("/api/v1/properties/7/descriptions/web-des-1", async () => {
          await held;
          return new HttpResponse(null, { status: 204 });
        }),
      );
      setup();

      const sub = await screen.findByRole("textbox", { name: "Web des 1" });
      await waitFor(() => expect((sub as HTMLTextAreaElement).value).not.toBe(""));
      await userEvent.type(screen.getByRole("textbox", { name: "Web des 2" }), "Draft para.");

      await userEvent.click(screen.getByRole("button", { name: "Clear Web des 1" }));
      const confirm = await screen.findByRole("dialog");
      await userEvent.click(within(confirm).getByRole("button", { name: /^clear$/i }));

      // The DELETE is still open: the para draft must not drop out of the guard.
      expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
      release();
      await waitFor(() => expect((sub as HTMLTextAreaElement).value).toBe(""));
      expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    });

    it("does not carry one villa's drafts onto another", async () => {
      // With the target's detail cached the layout keeps the Outlet mounted,
      // so nothing remounts the tab on its own — Save would then write one
      // villa's text onto the other.
      setReservationsUser();
      installBaseHandlers();
      server.use(
        http.get("/api/v1/properties/casa-mar", () =>
          HttpResponse.json({
            ...propertyFixture,
            id: 8,
            name: "Casa Mar",
            slug: "casa-mar",
            video_url: "",
          }),
        ),
        http.get("/api/v1/properties/8/descriptions", () =>
          HttpResponse.json(
            drfPage([{ id: 2, property: 8, section: "web_des_1", body: "The other villa." }]),
          ),
        ),
      );
      const { router } = setup();
      const webDes1 = () =>
        screen.getByRole("textbox", { name: "Web des 1" }) as HTMLTextAreaElement;
      await screen.findByRole("textbox", { name: "Web des 1" });
      await waitFor(() => expect(webDes1().value).toBe("A villa above the bay."));

      await router.navigate("/properties/casa-mar/descriptions");
      await waitFor(() => expect(webDes1().value).toBe("The other villa."));
      // Back to the first villa — now cached, so the Outlet is not remounted.
      await router.navigate("/properties/casa-sur/descriptions");
      await waitFor(() => expect(webDes1().value).toBe("A villa above the bay."));
      expect((screen.getByLabelText("Video URL") as HTMLInputElement).value).toBe(
        "https://video.example/casa-sur",
      );
      expect(screen.queryByText("Unsaved changes")).not.toBeInTheDocument();
    });

    it("still prompts when the descriptions fetch has failed", async () => {
      // The guard dialog is rendered in every branch: a dirty video URL must
      // never hold a navigation with no visible prompt.
      setReservationsUser();
      installBaseHandlers();
      server.use(
        http.get("/api/v1/properties/7/descriptions", () =>
          HttpResponse.json({ detail: "boom" }, { status: 500 }),
        ),
      );
      setup();

      expect(await screen.findByText(/Couldn't load descriptions/i)).toBeInTheDocument();
      await userEvent.type(screen.getByLabelText("Video URL"), "/tour");
      await userEvent.click(detailsTab());
      expect(
        await screen.findByRole("dialog", { name: "Discard unsaved changes?" }),
      ).toBeInTheDocument();
    });
  });

  describe("Video URL", () => {
    it("clearing PATCHes an empty string, not an omitted key (GAP-024 trap)", async () => {
      setReservationsUser();
      installBaseHandlers();
      let patchBody: Record<string, unknown> | null = null;
      server.use(
        http.patch("/api/v1/properties/7", async ({ request }) => {
          patchBody = (await request.json()) as Record<string, unknown>;
          return HttpResponse.json({ ...propertyFixture, video_url: "" });
        }),
      );
      setup();

      const video = await screen.findByLabelText("Video URL");
      await userEvent.clear(video);
      await userEvent.click(screen.getByRole("button", { name: "Save video URL" }));

      await waitFor(() => expect(patchBody).not.toBeNull());
      expect(patchBody).toEqual({ video_url: "" });
    });

    it("surfaces the backend's URL validation error inline", async () => {
      // The backend is the URL authority (URLField 400s a scheme-less value);
      // nothing client-side parses it, so the 400 must land on the field.
      setReservationsUser();
      installBaseHandlers();
      server.use(
        http.patch("/api/v1/properties/7", () =>
          HttpResponse.json(
            { detail: "Validation failed", field_errors: { video_url: ["Enter a valid URL."] } },
            { status: 400 },
          ),
        ),
      );
      setup();

      const video = await screen.findByLabelText("Video URL");
      await userEvent.clear(video);
      await userEvent.type(video, "vimeo.com/123");
      await userEvent.click(screen.getByRole("button", { name: "Save video URL" }));

      expect(await screen.findByText(/Enter a valid URL\./)).toBeInTheDocument();
      // Still a draft: the failed save must not read as persisted.
      expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    });

    it("is read-only without the reservations role", async () => {
      installBaseHandlers();
      setup();
      expect(await screen.findByLabelText("Video URL")).toBeDisabled();
      // Disabled, never hidden — the tooltip says why.
      expect(screen.getByRole("button", { name: "Save video URL" })).toBeDisabled();
    });
  });
});
