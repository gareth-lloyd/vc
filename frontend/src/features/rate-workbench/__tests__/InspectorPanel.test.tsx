import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";
import { InspectorPanel } from "../components/InspectorPanel";

const service = {
  id: 9,
  property: 7,
  name: "Daily maid",
  copy: "Daily maid service",
  notes: null,
  sort_order: 0,
  is_active: true,
  applies_from: null,
  applies_to: null,
};
const extra = {
  id: 11,
  property: 7,
  name: "Airport transfer",
  amount: "120",
  currency_code: "EUR",
  is_mandatory: false,
};
const discount = {
  id: 21,
  property: 7,
  name: "Early bird",
  code: "EARLY",
  kind: "percent",
  amount: "10",
};

function installReads() {
  server.use(
    http.get("/api/v1/properties/7/services", () => HttpResponse.json(drfPage([service]))),
    http.get("/api/v1/properties/7/extras", () => HttpResponse.json(drfPage([extra]))),
    http.get("/api/v1/properties/7/discounts", () => HttpResponse.json(drfPage([discount]))),
  );
}

function renderPanel(canWrite = true) {
  return renderWithProviders(
    <InspectorPanel propertyId={7} canWrite={canWrite} currencyCode="EUR" />,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("InspectorPanel", () => {
  it("renders the three sections with their items", async () => {
    installReads();
    renderPanel();
    expect(await screen.findByText("Daily maid")).toBeInTheDocument();
    expect(screen.getByText("Airport transfer")).toBeInTheDocument();
    expect(screen.getByText("Early bird")).toBeInTheDocument();
  });

  it("creates an extra via POST and refreshes the list", async () => {
    installReads();
    let created = false;
    const posted: unknown[] = [];
    server.use(
      http.post("/api/v1/properties/7/extras", async ({ request }) => {
        posted.push(await request.json());
        created = true;
        return HttpResponse.json({ id: 12, property: 7, name: "Cleaning", amount: "50" });
      }),
      // After invalidation the list refetches — return the new row too.
      http.get("/api/v1/properties/7/extras", () =>
        HttpResponse.json(
          drfPage(created ? [extra, { ...extra, id: 12, name: "Cleaning" }] : [extra]),
        ),
      ),
    );
    const user = userEvent.setup();
    renderPanel();

    await user.click(await screen.findByRole("button", { name: "Add extra" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Name"), "Cleaning");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]).toMatchObject({ name: "Cleaning" });
    expect(await screen.findByText("Cleaning")).toBeInTheDocument();
  });

  it("edits a discount via PATCH to the flat detail route", async () => {
    installReads();
    const patched: Array<{ id: string; body: unknown }> = [];
    server.use(
      http.patch("/api/v1/discounts/:id", async ({ params, request }) => {
        patched.push({ id: String(params.id), body: await request.json() });
        return HttpResponse.json({ ...discount, name: "Early bird 2" });
      }),
    );
    const user = userEvent.setup();
    renderPanel();

    const row = (await screen.findByText("Early bird")).closest("li");
    await user.click(within(row as HTMLElement).getByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog");
    const name = within(dialog).getByLabelText("Name");
    await user.clear(name);
    await user.type(name, "Early bird 2");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(patched).toHaveLength(1));
    expect(patched[0].id).toBe("21");
    expect(patched[0].body).toMatchObject({ name: "Early bird 2" });
  });

  it("deletes an inclusion via DELETE after confirm", async () => {
    installReads();
    const deleted: string[] = [];
    server.use(
      http.delete("/api/v1/services/:id", ({ params }) => {
        deleted.push(String(params.id));
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();
    renderPanel();

    // First "Delete" icon button belongs to the inclusions section (rendered first).
    await user.click((await screen.findAllByRole("button", { name: "Delete" }))[0]);
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(deleted).toEqual(["9"]));
  });

  it("disables the Add buttons for a read-only user", async () => {
    installReads();
    renderPanel(false);
    await screen.findByText("Daily maid");
    expect(screen.getByRole("button", { name: "Add inclusion" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Add extra" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Add discount" })).toBeDisabled();
    // No per-row edit/delete affordances either.
    expect(screen.queryByRole("button", { name: "Delete" })).toBeNull();
  });
});
