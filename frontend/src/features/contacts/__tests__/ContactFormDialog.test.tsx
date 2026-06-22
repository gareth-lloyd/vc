import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { ContactFormDialog } from "../components/ContactFormDialog";
import type { Contact } from "../schemas";

const createdContact = {
  id: 999,
  first_name: "Grace",
  last_name: "Hopper",
  status: "active",
  emails: [{ id: 1, email: "grace@example.com", is_primary: true }],
  phones: [],
};

describe("ContactFormDialog (create)", () => {
  it("blocks submit until a channel is supplied", async () => {
    let posted = false;
    server.use(
      http.post("/api/v1/contacts", () => {
        posted = true;
        return HttpResponse.json(createdContact, { status: 201 });
      }),
    );
    renderWithProviders(<ContactFormDialog open mode="create" onOpenChange={() => {}} />);

    await userEvent.type(await screen.findByLabelText(/^first name$/i), "Grace");
    await userEvent.click(screen.getByRole("button", { name: /create contact/i }));

    await waitFor(() => expect(screen.getByText(/reachable/i)).toBeInTheDocument());
    expect(posted).toBe(false);
  });

  it("folds the inline email into the POST body as a primary channel", async () => {
    let postedBody: unknown = null;
    server.use(
      http.post("/api/v1/contacts", async ({ request }) => {
        postedBody = await request.json();
        return HttpResponse.json(createdContact, { status: 201 });
      }),
    );
    renderWithProviders(<ContactFormDialog open mode="create" onOpenChange={() => {}} />);

    await userEvent.type(await screen.findByLabelText(/^first name$/i), "Grace");
    await userEvent.type(screen.getByLabelText(/^email$/i), "grace@example.com");
    await userEvent.click(screen.getByRole("button", { name: /create contact/i }));

    await waitFor(() => expect(postedBody).not.toBeNull());
    expect(postedBody).toMatchObject({
      first_name: "Grace",
      emails: [{ email: "grace@example.com", is_primary: true }],
    });
  });

  it("submits the agency selected in the picker as a PK (never `company`)", async () => {
    let postedBody: Record<string, unknown> | null = null;
    server.use(
      http.get("/api/v1/organisations", () =>
        HttpResponse.json({
          count: 1,
          next: null,
          previous: null,
          results: [{ id: 55, name: "Acme Travel", org_type: "agency", status: "active" }],
        }),
      ),
      http.post("/api/v1/contacts", async ({ request }) => {
        postedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(createdContact, { status: 201 });
      }),
    );
    renderWithProviders(<ContactFormDialog open mode="create" onOpenChange={() => {}} />);

    await userEvent.type(await screen.findByLabelText(/^first name$/i), "Grace");
    await userEvent.type(screen.getByLabelText(/^email$/i), "grace@example.com");

    // Open the agency picker, search, and pick the result.
    await userEvent.click(screen.getByRole("combobox"));
    await userEvent.type(screen.getByLabelText(/search companies/i), "Acme");
    await userEvent.click(await screen.findByRole("option", { name: /Acme Travel/i }));

    await userEvent.click(screen.getByRole("button", { name: /create contact/i }));

    await waitFor(() => expect(postedBody).not.toBeNull());
    expect(postedBody).toMatchObject({ first_name: "Grace", agency: 55 });
    expect(postedBody).not.toHaveProperty("company");
  });
});

describe("ContactFormDialog (edit)", () => {
  const editContact: Contact = {
    id: 7,
    first_name: "Ada",
    last_name: "Lovelace",
    agency: 100,
    agency_detail: { id: 100, name: "Analytical Engines", org_type: "agency", status: "active" },
    status: "active",
    emails: [],
    phones: [],
  };

  it("detaches the agency and PATCHes agency: null", async () => {
    let patchedBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/contacts/7", async ({ request }) => {
        patchedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...editContact, agency: null, agency_detail: null });
      }),
    );
    renderWithProviders(
      <ContactFormDialog
        open
        mode="edit"
        contactId={7}
        contact={editContact}
        onOpenChange={() => {}}
      />,
    );

    // The picker is seeded from agency_detail; Clear detaches it.
    expect(await screen.findByRole("combobox")).toHaveTextContent("Analytical Engines");
    await userEvent.click(screen.getByRole("button", { name: /^clear$/i }));
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(patchedBody).not.toBeNull());
    expect(patchedBody).toMatchObject({ agency: null });
  });
});
