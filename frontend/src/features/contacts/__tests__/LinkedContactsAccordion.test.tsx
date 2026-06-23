import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";
import { useAuthStore } from "@/features/auth/store";
import { LinkedContactsAccordion } from "../components/LinkedContactsAccordion";

const outgoing = {
  id: 1,
  kind: "child",
  kind_label: "Child",
  note: "",
  other_person: {
    id: 11,
    first_name: "Bobby",
    last_name: "Junior",
    display_name: "Bobby Junior",
    kind: "customer",
  },
  direction: "outgoing" as const,
  created_at: "2026-01-01T00:00:00Z",
};

const incoming = {
  id: 2,
  kind: "child",
  kind_label: "Child",
  note: "",
  other_person: {
    id: 12,
    first_name: "Mary",
    last_name: "Senior",
    display_name: "Mary Senior",
    kind: "customer",
  },
  direction: "incoming" as const,
  created_at: "2026-01-02T00:00:00Z",
};

beforeEach(() => {
  // The remove affordance is gated on the reservations role.
  useAuthStore.setState({ role: "RESERVATIONS", isSuperuser: false });
});

afterEach(() => {
  useAuthStore.getState().clear();
});

async function expand() {
  await userEvent.click(await screen.findByRole("button", { name: /linked contacts/i }));
}

describe("LinkedContactsAccordion", () => {
  it("renders the count in the header", async () => {
    server.use(
      http.get("/api/v1/contacts/5/relationships", () =>
        HttpResponse.json(drfPage([outgoing, incoming])),
      ),
    );
    renderWithProviders(<LinkedContactsAccordion contactId={5} />);

    expect(
      await screen.findByRole("button", { name: /linked contacts \(2\)/i }),
    ).toBeInTheDocument();
  });

  it("renders the forward label for an outgoing row", async () => {
    server.use(
      http.get("/api/v1/contacts/5/relationships", () => HttpResponse.json(drfPage([outgoing]))),
    );
    renderWithProviders(<LinkedContactsAccordion contactId={5} />);
    await expand();

    const row = (await screen.findByText("Bobby Junior")).closest("li") as HTMLElement;
    expect(within(row).getByText("Child")).toBeInTheDocument();
  });

  it("renders the INVERSE label for an incoming row (child → Parent)", async () => {
    server.use(
      http.get("/api/v1/contacts/5/relationships", () => HttpResponse.json(drfPage([incoming]))),
    );
    renderWithProviders(<LinkedContactsAccordion contactId={5} />);
    await expand();

    const row = (await screen.findByText("Mary Senior")).closest("li") as HTMLElement;
    expect(within(row).getByText("Parent")).toBeInTheDocument();
    expect(within(row).queryByText("Child")).not.toBeInTheDocument();
  });

  it("removes a link via DELETE", async () => {
    let deleted = false;
    server.use(
      http.get("/api/v1/contacts/5/relationships", () => HttpResponse.json(drfPage([outgoing]))),
      http.delete("/api/v1/contacts/5/relationships/1", () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderWithProviders(<LinkedContactsAccordion contactId={5} />);
    await expand();

    const row = (await screen.findByText("Bobby Junior")).closest("li") as HTMLElement;
    await userEvent.click(within(row).getByRole("button", { name: /actions/i }));
    await userEvent.click(await screen.findByRole("menuitem", { name: /remove/i }));
    await userEvent.click(await screen.findByRole("button", { name: /^remove$/i }));

    await waitFor(() => expect(deleted).toBe(true));
  });

  it("shows the empty state when there are no links", async () => {
    server.use(http.get("/api/v1/contacts/5/relationships", () => HttpResponse.json(drfPage([]))));
    renderWithProviders(<LinkedContactsAccordion contactId={5} />);
    await expand();

    expect(await screen.findByText(/no linked contacts yet/i)).toBeInTheDocument();
  });
});
