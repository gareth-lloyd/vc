import { useState } from "react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";
import { ContactPicker } from "../components/ContactPicker";
import type { Contact } from "../schemas";

const alice: Contact = {
  id: 101,
  first_name: "Alice",
  last_name: "Owner",
  emails: [{ id: 11, email: "alice@example.com", is_primary: true }],
  phones: [],
};

const bob: Contact = {
  id: 102,
  first_name: "Bob",
  last_name: "Agent",
  emails: [],
  phones: [],
};

function Wrapper({
  onCreateNew,
  kind,
}: {
  onCreateNew?: () => void;
  kind?: "contact" | "customer";
}) {
  const [value, setValue] = useState<Contact | null>(null);
  return <ContactPicker value={value} onChange={setValue} onCreateNew={onCreateNew} kind={kind} />;
}

describe("ContactPicker", () => {
  it("shows search results after typing at least 2 characters", async () => {
    server.use(
      http.get("/api/v1/contacts", ({ request }) => {
        const url = new URL(request.url);
        const q = url.searchParams.get("search") ?? "";
        if (q.includes("ali")) return HttpResponse.json(drfPage([alice]));
        return HttpResponse.json(drfPage([]));
      }),
    );

    renderWithProviders(<Wrapper />);
    await userEvent.click(screen.getByRole("combobox"));
    const input = screen.getByLabelText(/search contacts/i);
    await userEvent.type(input, "ali");
    expect(await screen.findByText("Alice Owner")).toBeInTheDocument();
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
  });

  it("filters the search to business contacts (kind=contact), never customers", async () => {
    // GAP-045 D2: /contacts now includes customer mirrors; the assignment picker
    // must scope to kind=contact so a customer can't be assigned as an owner/agent.
    let capturedKind: string | null = null;
    server.use(
      http.get("/api/v1/contacts", ({ request }) => {
        capturedKind = new URL(request.url).searchParams.get("kind");
        return HttpResponse.json(drfPage([alice]));
      }),
    );

    renderWithProviders(<Wrapper />);
    await userEvent.click(screen.getByRole("combobox"));
    await userEvent.type(screen.getByLabelText(/search contacts/i), "ali");
    await screen.findByText("Alice Owner");
    expect(capturedKind).toBe("contact");
  });

  it("scopes the search to the given kind (customer) when asked", async () => {
    // The enquiry picker passes kind=customer to offer linkable clients, not
    // business contacts. The query string must carry that scope through.
    let capturedKind: string | null = null;
    server.use(
      http.get("/api/v1/contacts", ({ request }) => {
        capturedKind = new URL(request.url).searchParams.get("kind");
        return HttpResponse.json(drfPage([alice]));
      }),
    );

    renderWithProviders(<Wrapper kind="customer" />);
    await userEvent.click(screen.getByRole("combobox"));
    await userEvent.type(screen.getByLabelText(/search contacts/i), "ali");
    await screen.findByText("Alice Owner");
    expect(capturedKind).toBe("customer");
  });

  it("selects a contact and closes the popover", async () => {
    server.use(http.get("/api/v1/contacts", () => HttpResponse.json(drfPage([alice, bob]))));

    renderWithProviders(<Wrapper />);
    await userEvent.click(screen.getByRole("combobox"));
    await userEvent.type(screen.getByLabelText(/search contacts/i), "al");
    await userEvent.click(await screen.findByText("Alice Owner"));
    await waitFor(() => expect(screen.getByRole("combobox")).toHaveTextContent("Alice Owner"));
  });

  it("shows empty state when no results", async () => {
    server.use(http.get("/api/v1/contacts", () => HttpResponse.json(drfPage([]))));

    renderWithProviders(<Wrapper />);
    await userEvent.click(screen.getByRole("combobox"));
    await userEvent.type(screen.getByLabelText(/search contacts/i), "zzz");
    expect(await screen.findByText(/no contacts found/i)).toBeInTheDocument();
  });

  it("shows minimum character hint before typing enough", async () => {
    renderWithProviders(<Wrapper />);
    await userEvent.click(screen.getByRole("combobox"));
    expect(screen.getByText(/type at least 2 characters/i)).toBeInTheDocument();
  });

  it("calls onCreateNew when 'Create new contact' is clicked", async () => {
    const onCreateNew = vi.fn();
    renderWithProviders(<Wrapper onCreateNew={onCreateNew} />);
    await userEvent.click(screen.getByRole("combobox"));
    await userEvent.click(screen.getByText(/create new contact/i));
    expect(onCreateNew).toHaveBeenCalledOnce();
  });
});
