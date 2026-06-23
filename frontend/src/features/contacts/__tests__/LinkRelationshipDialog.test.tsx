import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { toast } from "sonner";
import { LinkRelationshipDialog } from "../components/LinkRelationshipDialog";

beforeEach(() => {
  vi.mocked(toast.success).mockReset();
  vi.mocked(toast.error).mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

const candidate = {
  id: 42,
  first_name: "Grace",
  last_name: "Hopper",
  status: "active",
  emails: [],
  phones: [],
};

function mockSearch() {
  return http.get("/api/v1/contacts", () => HttpResponse.json(drfPage([candidate])));
}

async function pickContactAndKind() {
  // Two comboboxes: the ContactPicker trigger (first) and the kind Select
  // trigger (carries aria-label "Relationship"). Pick Grace, then Spouse.
  const pickerTrigger = screen
    .getAllByRole("combobox")
    .find((el) => el.getAttribute("aria-label") !== "Relationship")!;
  await userEvent.click(pickerTrigger);
  await userEvent.type(screen.getByLabelText(/search contacts/i), "Grace");
  await userEvent.click(await screen.findByRole("option", { name: /Grace Hopper/i }));

  await userEvent.click(screen.getByRole("combobox", { name: "Relationship" }));
  await userEvent.click(await screen.findByRole("option", { name: /^spouse$/i }));
}

describe("LinkRelationshipDialog", () => {
  it("POSTs { to_person, kind, note } when a contact and kind are chosen", async () => {
    let postedBody: Record<string, unknown> | null = null;
    server.use(
      mockSearch(),
      http.post("/api/v1/contacts/7/relationships", async ({ request }) => {
        postedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...candidate, id: 100, kind: "spouse" }, { status: 201 });
      }),
    );
    renderWithProviders(<LinkRelationshipDialog contactId={7} open onOpenChange={() => {}} />);

    await pickContactAndKind();
    await userEvent.type(screen.getByLabelText(/^note$/i), "met at conference");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(postedBody).not.toBeNull());
    expect(postedBody).toEqual({
      to_person: 42,
      kind: "spouse",
      note: "met at conference",
    });
  });

  it("surfaces a 400 non_field 'duplicate' error in the banner", async () => {
    server.use(
      mockSearch(),
      http.post("/api/v1/contacts/7/relationships", () =>
        HttpResponse.json(
          {
            detail: "Validation failed",
            field_errors: { non_field_errors: ["This relationship already exists."] },
          },
          { status: 400 },
        ),
      ),
    );
    renderWithProviders(<LinkRelationshipDialog contactId={7} open onOpenChange={() => {}} />);

    await pickContactAndKind();
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    expect(await screen.findByText(/already exists/i)).toBeInTheDocument();
  });

  it("opens the inline create-contact dialog without closing itself", async () => {
    // Regression: 'create new' must NOT unmount this dialog (the parent gates the
    // mount on `open`), or the nested ContactFormDialog dies with it.
    server.use(mockSearch());
    renderWithProviders(<LinkRelationshipDialog contactId={7} open onOpenChange={() => {}} />);

    const pickerTrigger = screen
      .getAllByRole("combobox")
      .find((el) => el.getAttribute("aria-label") !== "Relationship")!;
    await userEvent.click(pickerTrigger);
    await userEvent.click(await screen.findByRole("button", { name: /create new contact/i }));

    // The create dialog appeared (its heading) AND the link dialog (its kind
    // Select) is still mounted — `hidden: true` because the modal create dialog
    // aria-hides the background link dialog, which is exactly what we want: it
    // stayed mounted underneath rather than unmounting.
    expect(await screen.findByRole("heading", { name: /^create contact$/i })).toBeInTheDocument();
    expect(
      screen.getByRole("combobox", { name: "Relationship", hidden: true }),
    ).toBeInTheDocument();
  });

  it("blocks Save with no contact picked (no POST)", async () => {
    let posted = false;
    server.use(
      mockSearch(),
      http.post("/api/v1/contacts/7/relationships", () => {
        posted = true;
        return HttpResponse.json({ ...candidate, id: 100, kind: "spouse" }, { status: 201 });
      }),
    );
    renderWithProviders(<LinkRelationshipDialog contactId={7} open onOpenChange={() => {}} />);

    // Choose a kind but NOT a contact, then Save.
    await userEvent.click(screen.getByRole("combobox", { name: "Relationship" }));
    await userEvent.click(await screen.findByRole("option", { name: /^spouse$/i }));
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    expect(await screen.findByText(/choose a contact/i)).toBeInTheDocument();
    expect(posted).toBe(false);
  });

  it("toasts on a 5xx server error", async () => {
    server.use(
      mockSearch(),
      http.post("/api/v1/contacts/7/relationships", () =>
        HttpResponse.json({ detail: "Boom" }, { status: 500 }),
      ),
    );
    renderWithProviders(<LinkRelationshipDialog contactId={7} open onOpenChange={() => {}} />);

    await pickContactAndKind();
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Something went wrong"));
  });
});
