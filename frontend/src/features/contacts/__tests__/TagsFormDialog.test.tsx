import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { toast } from "sonner";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { TagsFormDialog } from "../components/TagsFormDialog";

beforeEach(() => {
  vi.mocked(toast.success).mockClear();
  vi.mocked(toast.error).mockClear();
});

describe("TagsFormDialog", () => {
  it("renders a checkbox per taxonomy entry, pre-checked from current tags", async () => {
    renderWithProviders(
      <TagsFormDialog contactId={5} tags={["vip"]} open onOpenChange={() => {}} />,
    );

    const vip = await screen.findByRole("checkbox", { name: "VIP" });
    const trade = screen.getByRole("checkbox", { name: "Trade" });
    expect(vip).toBeChecked();
    expect(trade).not.toBeChecked();
    // 10 fixed-taxonomy values, "Repeat" excluded.
    expect(screen.getAllByRole("checkbox")).toHaveLength(10);
  });

  it("PATCHes the full selected set on save", async () => {
    let patchedBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/contacts/5", async ({ request }) => {
        patchedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 5, tags: patchedBody.tags });
      }),
    );
    renderWithProviders(
      <TagsFormDialog contactId={5} tags={["vip"]} open onOpenChange={() => {}} />,
    );

    await userEvent.click(await screen.findByRole("checkbox", { name: "Trade" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "VIP" }));
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(patchedBody).not.toBeNull());
    expect(patchedBody).toEqual({ tags: ["trade"] });
    expect(toast.success).toHaveBeenCalled();
  });

  it("maps a 4xx field error on tags to an inline message and does NOT toast", async () => {
    server.use(
      http.patch("/api/v1/contacts/5", () =>
        HttpResponse.json(
          { detail: "Invalid", field_errors: { tags: ["Unknown tag."] } },
          { status: 400 },
        ),
      ),
    );
    renderWithProviders(<TagsFormDialog contactId={5} tags={[]} open onOpenChange={() => {}} />);

    await userEvent.click(await screen.findByRole("checkbox", { name: "VIP" }));
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    expect(await screen.findByText(/unknown tag/i)).toBeInTheDocument();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("toasts on a 5xx and keeps the dialog open", async () => {
    let closed = false;
    server.use(http.patch("/api/v1/contacts/5", () => new HttpResponse(null, { status: 500 })));
    renderWithProviders(
      <TagsFormDialog
        contactId={5}
        tags={[]}
        open
        onOpenChange={(o) => {
          if (!o) closed = true;
        }}
      />,
    );

    await userEvent.click(await screen.findByRole("checkbox", { name: "VIP" }));
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(closed).toBe(false);
  });
});
