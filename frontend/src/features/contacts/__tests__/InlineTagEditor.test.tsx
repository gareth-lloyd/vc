import { delay, http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { toast } from "sonner";
import { server } from "@/test/msw/server";
import { createTestQueryClient, renderWithProviders } from "@/test/render";
import { queryKeys } from "@/lib/query/keys";
import { useAuthStore } from "@/features/auth/store";
import { useContact } from "../hooks";
import { InlineTagEditor } from "../components/InlineTagEditor";

// Renders the editor wired to the contact-detail cache (as it is in production
// via the outlet/useContact), so optimistic cache updates surface in the boxes.
function EditorViaCache({ contactId }: { contactId: number }) {
  const { data } = useContact(contactId);
  if (!data) return null;
  return <InlineTagEditor contactId={contactId} tags={data.tags ?? []} />;
}

const baseUser = {
  id: 1,
  email: "writer@example.com",
  first_name: "Wri",
  last_name: "Ter",
  is_active: true,
  is_staff: true,
  is_superuser: false,
  preferred_language: "en",
};

function grantWriterRole() {
  useAuthStore.setState({
    user: { ...baseUser, role: "RESERVATIONS" },
    role: "RESERVATIONS",
    isSuperuser: false,
    permissions: [],
    status: "authenticated",
    pendingTfa: null,
  });
}

function clearRole() {
  useAuthStore.setState({
    user: { ...baseUser, role: null },
    role: null,
    isSuperuser: false,
    permissions: [],
    status: "authenticated",
    pendingTfa: null,
  });
}

beforeEach(() => {
  grantWriterRole();
  vi.mocked(toast.error).mockClear();
});

afterEach(() => {
  useAuthStore.setState({ user: null, role: null, status: "unauthenticated" });
});

describe("InlineTagEditor", () => {
  it("PATCHes the new full set when a tag is checked (no dialog, no save button)", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/contacts/7", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 7, tags: body.tags });
      }),
    );
    renderWithProviders(<InlineTagEditor contactId={7} tags={[]} />);

    await userEvent.click(screen.getByRole("button", { name: /edit tags/i }));
    await userEvent.click(await screen.findByRole("checkbox", { name: "VIP" }));

    await waitFor(() => expect(body).toEqual({ tags: ["vip"] }));
    // No "Save" affordance — the toggle itself persists.
    expect(screen.queryByRole("button", { name: /^save$/i })).not.toBeInTheDocument();
  });

  it("PATCHes the remaining set when a tag is unchecked", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/contacts/7", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 7, tags: body.tags });
      }),
    );
    renderWithProviders(<InlineTagEditor contactId={7} tags={["vip", "trade"]} />);

    await userEvent.click(screen.getByRole("button", { name: /edit tags/i }));
    await userEvent.click(await screen.findByRole("checkbox", { name: "VIP" }));

    await waitFor(() => expect(body).toEqual({ tags: ["trade"] }));
  });

  it("is read-only without the reservations role (button disabled, never gone)", () => {
    clearRole();
    renderWithProviders(<InlineTagEditor contactId={7} tags={["vip"]} />);

    expect(screen.getByText("VIP")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /edit tags/i })).toBeDisabled();
  });

  it("optimistically checks the box, then rolls back and toasts on a 5xx", async () => {
    const fixture = { id: 7, status: "active", emails: [], phones: [], tags: [] as string[] };
    const queryClient = createTestQueryClient();
    queryClient.setQueryData(queryKeys.contacts.detail(7), fixture);
    server.use(
      http.get("/api/v1/contacts/7", () => HttpResponse.json(fixture)),
      // Delay so the optimistic window is observable before the rollback.
      http.patch("/api/v1/contacts/7", async () => {
        await delay(40);
        return new HttpResponse(null, { status: 500 });
      }),
    );
    renderWithProviders(<EditorViaCache contactId={7} />, { queryClient });

    await userEvent.click(screen.getByRole("button", { name: /edit tags/i }));
    await userEvent.click(await screen.findByRole("checkbox", { name: "VIP" }));

    // Optimistic: the box reflects the toggle immediately (cache-driven).
    await waitFor(() => expect(screen.getByRole("checkbox", { name: "VIP" })).toBeChecked());
    // 5xx → cache rolls back to the snapshot and the failure toasts.
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByRole("checkbox", { name: "VIP" })).not.toBeChecked());
  });
});
