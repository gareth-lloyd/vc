import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { expectTriggerRange, openDateRange, typeDateRange } from "@/test/dateRange";
import { renderWithProviders } from "@/test/render";
import { AssignmentFormDialog } from "../components/AssignmentFormDialog";
import type { PropertyContactAssignment } from "../schemas";
import type { Contact } from "@/features/contacts/schemas";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { toast } from "sonner";

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

afterEach(() => {
  vi.mocked(toast.success).mockClear();
  vi.mocked(toast.error).mockClear();
});

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
        return HttpResponse.json(assignmentFixture, { status: 201 });
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

  it("posts an untouched (fully optional) window as explicit nulls", async () => {
    let postBody: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/properties/5/contacts", async ({ request }) => {
        postBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          { ...assignmentFixture, id: 10, start_date: null, end_date: null },
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
    // The "" create defaults cross the wire as explicit null — DRF rejects ""
    // as an invalid date, and dropped keys couldn't clear anything on PATCH.
    expect(postBody!.start_date).toBeNull();
    expect(postBody!.end_date).toBeNull();
  });

  it("surfaces a 400 field error inline (no toast)", async () => {
    server.use(
      http.post("/api/v1/properties/5/contacts", () =>
        HttpResponse.json(
          {
            code: "validation_error",
            detail: "Validation failed",
            field_errors: { role: ["This contact is already assigned as owner."] },
          },
          { status: 400 },
        ),
      ),
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

    expect(await screen.findByText(/already assigned as owner/i)).toBeInTheDocument();
    expect(screen.getByText(/Validation failed/i)).toBeInTheDocument();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("falls back to an error toast on a 500", async () => {
    server.use(
      http.post("/api/v1/properties/5/contacts", () =>
        HttpResponse.json({ detail: "Internal server error" }, { status: 500 }),
      ),
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

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(toast.success).not.toHaveBeenCalled();
  });
});

describe("AssignmentFormDialog — edit", () => {
  it("prefills the trigger from the assignment and PATCHes cleared dates as explicit nulls", async () => {
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
    // PIN: the PATCH mapping sends cleared dates as explicit null (never ""
    // nor omitted keys, so they actually clear) and never sends `contact` —
    // see AssignmentFormDialog handleSubmit.
    expect(patchBody).toEqual({
      role: "owner",
      start_date: null,
      end_date: null,
      is_primary: false,
    });
  });
});
