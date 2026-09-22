import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";
import { precedes } from "@/test/dom";
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

const houseRulesRecord = {
  id: 1,
  property: 7,
  section: "house_rules",
  body: "No smoking indoors.",
  updated_at: "2026-05-01T00:00:00Z",
};

/** Every editor on the tab, top to bottom: the website order, notes last. */
const EDITOR_NAMES = [
  "Web des 1",
  "Web des 2",
  "Interior subtitle",
  "Interior paragraph",
  "Exterior subtitle",
  "Exterior paragraph",
  "Location subtitle",
  "Location paragraph",
  "Rooms",
  "House rules",
  "Internal notes",
];

const textbox = (name: string) => screen.getByRole("textbox", { name }) as HTMLTextAreaElement;

describe("DescriptionsSection", () => {
  it("stacks every section in website order with its hint, internal notes last", async () => {
    // One column, no sub-tabs: reviewing a villa's copy used to mean clicking
    // through seven tabs. The order is the public site's, so a reviewer reads
    // the page as a guest would; the parenthetical hints say where each piece
    // shows (or, for house rules, that it never does).
    setReservationsUser();
    server.use(
      http.get("/api/v1/properties/7/descriptions", () =>
        HttpResponse.json(
          drfPage([
            { id: 8, property: 7, section: "interior_sub", body: "Ensuite bedrooms." },
            { id: 9, property: 7, section: "interior_para", body: "Soft linen throughout." },
            { id: 6, property: 7, section: "rooms", body: "Five en-suite bedrooms." },
            houseRulesRecord,
          ]),
        ),
      ),
    );
    renderWithProviders(<DescriptionsSection propertyId={7} />);

    await waitFor(() => expect(textbox("Interior subtitle").value).toBe("Ensuite bedrooms."));
    expect(screen.queryByRole("tab")).not.toBeInTheDocument();
    const boxes = screen.getAllByRole("textbox");
    expect(boxes).toHaveLength(EDITOR_NAMES.length);
    EDITOR_NAMES.forEach((name, i) => expect(boxes[i]).toBe(textbox(name)));

    // Both halves of a former block are separately editable (GAP-090); a
    // subtitle — `web_des_1` is the top one — gets a short box, a paragraph a
    // tall one.
    expect(textbox("Interior paragraph").value).toBe("Soft linen throughout.");
    expect(textbox("Web des 1")).toHaveAttribute("rows", "3");
    expect(textbox("Interior subtitle")).toHaveAttribute("rows", "3");
    expect(textbox("Interior paragraph")).toHaveAttribute("rows", "8");
    expect(textbox("Rooms").value).toBe("Five en-suite bedrooms.");
    expect(textbox("House rules").value).toBe("No smoking indoors.");

    // Hints sit beside the label, outside it: the accessible name stays short
    // ("Save House rules", "Clear House rules?"), the hint is still read out.
    expect(screen.getByText("(top larger text)")).toBeInTheDocument();
    expect(screen.getByText("(opening paragraph)")).toBeInTheDocument();
    expect(screen.getByText("(shown under bedrooms online)")).toBeInTheDocument();
    const houseRulesHint = screen.getByText("(not shown online, included in booking)");
    expect(textbox("House rules")).toHaveAccessibleDescription(
      "(not shown online, included in booking)",
    );
    expect(houseRulesHint.closest("label")).toBeNull();
    useAuthStore.getState().clear();
  });

  it("ignores rows it doesn't render without taking the panel down", async () => {
    // Regression (GAP-062): the schema once pinned four sections while the
    // backend had six, so any extra row threw a ZodError that React Query
    // doesn't retry — collapsing the whole panel to "Couldn't load
    // descriptions". `other_information` is edited on the Features tab
    // (GAP-091), `overview` was retired (its rows are gone from the backend,
    // but an older cache may still echo one), and a newer backend may add
    // sections this build has never heard of. None of them render; none of
    // them break the ones that do.
    setReservationsUser();
    server.use(
      http.get("/api/v1/properties/7/descriptions", () =>
        HttpResponse.json(
          drfPage([
            { id: 2, property: 7, section: "location_sub", body: "Ten minutes from Chania." },
            { id: 5, property: 7, section: "other_information", body: "Pets on request." },
            { id: 1, property: 7, section: "overview", body: "Welcome to Casa Sur." },
            { id: 3, property: 7, section: "something_new", body: "From a newer backend." },
          ]),
        ),
      ),
    );
    renderWithProviders(<DescriptionsSection propertyId={7} />);

    await waitFor(() =>
      expect(textbox("Location subtitle").value).toBe("Ten minutes from Chania."),
    );
    expect(screen.getAllByRole("textbox")).toHaveLength(EDITOR_NAMES.length);
    expect(screen.queryByDisplayValue("Pets on request.")).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue("Welcome to Casa Sur.")).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue("From a newer backend.")).not.toBeInTheDocument();
    expect(screen.queryByText(/Couldn't load descriptions/i)).not.toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("renders the video section between the copy and internal notes", async () => {
    // The tab hands its video editor in as a node so it can sit where the
    // operator expects it — after the website copy, before the staff notes —
    // without the video form's state moving into this component.
    setReservationsUser();
    server.use(
      http.get("/api/v1/properties/7/descriptions", () =>
        HttpResponse.json(drfPage([houseRulesRecord])),
      ),
    );
    renderWithProviders(
      <DescriptionsSection propertyId={7} videoSection={<div>video-stub</div>} />,
    );

    await waitFor(() => expect(textbox("House rules").value).toBe("No smoking indoors."));
    const video = screen.getByText("video-stub");
    expect(precedes(textbox("House rules"), video)).toBe(true);
    expect(precedes(video, textbox("Internal notes"))).toBe(true);
    useAuthStore.getState().clear();
  });

  it("keeps the video section while descriptions load and after they fail", async () => {
    // The video URL is a property field, not a description: a failed
    // descriptions fetch must not hide its editor (DescriptionsTab types into
    // it after a 500). Internal notes stay hidden until loaded — with
    // unseeded bodies a Save there would overwrite notes that never arrived.
    setReservationsUser();
    server.use(
      http.get("/api/v1/properties/7/descriptions", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    renderWithProviders(
      <DescriptionsSection propertyId={7} videoSection={<div>video-stub</div>} />,
    );

    expect(screen.getByText("video-stub")).toBeInTheDocument();
    expect(await screen.findByText(/Couldn't load descriptions/i)).toBeInTheDocument();
    expect(screen.getByText("video-stub")).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("keeps internal notes apart from the website copy and saves them separately", async () => {
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
    expect(notes).toBe(textbox("Internal notes"));
    expect(screen.getByText("Not shown to guests")).toBeInTheDocument();

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
        HttpResponse.json(drfPage([houseRulesRecord])),
      ),
      http.delete(
        "/api/v1/properties/7/descriptions/house-rules",
        () => new HttpResponse(null, { status: 204 }),
      ),
    );
    renderWithProviders(<DescriptionsSection propertyId={7} />);

    const textarea = (await screen.findByRole("textbox", {
      name: "House rules",
    })) as HTMLTextAreaElement;
    await waitFor(() => expect(textarea.value).toBe("No smoking indoors."));

    // Every button names its section: eleven editors share one column and
    // all read "Clear", and Clear is a hard DELETE. The name is the short
    // label — no hint — so the dialog asks "Clear House rules?".
    await userEvent.click(screen.getByRole("button", { name: "Clear House rules" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Clear House rules?")).toBeInTheDocument();
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
    const textarea = await screen.findByRole("textbox", { name: "House rules" });
    await userEvent.type(textarea, "No smoking.");
    await userEvent.click(screen.getByRole("button", { name: "Save House rules" }));
    await waitFor(() => expect(putBody).not.toBeNull());
    expect(putBody!.body).toBe("No smoking.");
    useAuthStore.getState().clear();
  });
});
