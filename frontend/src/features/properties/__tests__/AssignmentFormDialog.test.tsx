import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { expectTriggerRange, openDateRange, typeDateRange } from "@/test/dateRange";
import { renderWithProviders } from "@/test/render";
import { AssignmentFormDialog } from "../components/AssignmentFormDialog";
import type { PropertyContactAssignment } from "../schemas";
import type { Contact } from "@/features/contacts/schemas";

// The picker's popover inputs reuse the existing per-field labels.
const ASSIGNMENT_DATE_LABELS = { from: /^start date$/i, to: /^end date$/i };

const contactFixture: Contact = {
  id: 101,
  first_name: "Alice",
  last_name: "Owner",
  emails: [],
  phones: [],
};

const assignmentFixture: PropertyContactAssignment = {
  id: 9,
  property: 5,
  contact: 101,
  role: "owner",
  start_date: "2026-03-01",
  end_date: "2026-08-31",
  is_primary: false,
};

async function chooseRole(name: string) {
  await userEvent.click(await screen.findByRole("combobox", { name: /role/i }));
  await userEvent.click(await screen.findByRole("option", { name }));
}

describe("AssignmentFormDialog — create", () => {
  it("picks a tenure window in the popover and posts both dates", async () => {
    let postBody: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/properties/5/contacts", async ({ request }) => {
        postBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          {
            id: 9,
            property: 5,
            contact: 101,
            role: "owner",
            start_date: "2026-03-01",
            end_date: "2026-08-31",
            is_primary: false,
          },
          { status: 201 },
        );
      }),
    );

    renderWithProviders(
      <AssignmentFormDialog
        propertyId={5}
        open
        onOpenChange={() => {}}
        mode="create"
        initialContact={contactFixture}
      />,
    );

    await chooseRole("Owner");
    const picker = await openDateRange(userEvent, /^dates/i);
    await typeDateRange(
      userEvent,
      picker,
      { from: "2026-03-01", to: "2026-08-31" },
      ASSIGNMENT_DATE_LABELS,
    );
    // Days mode: the tenure covers both endpoint days (inclusive).
    expectTriggerRange(/^dates/i, "1 Mar – 31 Aug 2026 · 184 days");
    await userEvent.click(screen.getByRole("button", { name: /^save contact$/i }));

    await waitFor(() => expect(postBody).not.toBeNull());
    expect(postBody!.contact).toBe(101);
    expect(postBody!.role).toBe("owner");
    expect(postBody!.start_date).toBe("2026-03-01");
    expect(postBody!.end_date).toBe("2026-08-31");
  });

  it("posts an untouched (fully optional) window as empty strings verbatim", async () => {
    let postBody: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/properties/5/contacts", async ({ request }) => {
        postBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          {
            id: 10,
            property: 5,
            contact: 101,
            role: "owner",
            start_date: null,
            end_date: null,
            is_primary: false,
          },
          { status: 201 },
        );
      }),
    );

    renderWithProviders(
      <AssignmentFormDialog
        propertyId={5}
        open
        onOpenChange={() => {}}
        mode="create"
        initialContact={contactFixture}
      />,
    );

    await chooseRole("Owner");
    await userEvent.click(screen.getByRole("button", { name: /^save contact$/i }));

    await waitFor(() => expect(postBody).not.toBeNull());
    // PIN: the create defaults are "" and the submit sends them verbatim —
    // never null, never dropped keys (no empty→null mapping exists).
    expect(postBody!.start_date).toBe("");
    expect(postBody!.end_date).toBe("");
  });
});

describe("AssignmentFormDialog — edit", () => {
  it("prefills the trigger from the assignment and PATCHes cleared dates as empty strings verbatim", async () => {
    let patchBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/properties/5/contacts/9", async ({ request }) => {
        patchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          ...assignmentFixture,
          start_date: null,
          end_date: null,
        });
      }),
    );

    renderWithProviders(
      <AssignmentFormDialog
        propertyId={5}
        open
        onOpenChange={() => {}}
        mode="edit"
        assignment={assignmentFixture}
        contact={contactFixture}
      />,
    );

    // The stored tenure window prefills the picker trigger.
    expectTriggerRange(/^dates/i, "1 Mar – 31 Aug 2026 · 184 days");

    // Both ends are fully optional: clear the whole window via the popover's
    // typed inputs (a calendar click always writes a closed range).
    const picker = await openDateRange(userEvent, /^dates/i);
    await waitFor(() =>
      expect(picker.getByLabelText(ASSIGNMENT_DATE_LABELS.from)).toHaveValue("2026-03-01"),
    );
    await typeDateRange(userEvent, picker, { from: "", to: "" }, ASSIGNMENT_DATE_LABELS);
    await userEvent.click(screen.getByRole("button", { name: /^update assignment$/i }));

    await waitFor(() => expect(patchBody).not.toBeNull());
    // PIN: the PATCH mapping sends "" verbatim (never null) and never sends
    // `contact` — see AssignmentFormDialog handleSubmit.
    expect(patchBody).toEqual({
      role: "owner",
      start_date: "",
      end_date: "",
      is_primary: false,
    });
  });
});
