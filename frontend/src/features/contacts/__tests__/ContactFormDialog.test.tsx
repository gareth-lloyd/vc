import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { ContactFormDialog } from "../components/ContactFormDialog";

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
});
