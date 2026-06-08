import { useState } from "react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";
import { GuestPicker } from "../components/GuestPicker";
import type { Guest } from "../schemas";

const ada: Guest = {
  id: 101,
  first_name: "Ada",
  last_name: "Lovelace",
  email: "ada@example.com",
  phone: "",
  status: "active",
};

const grace: Guest = {
  id: 102,
  first_name: "Grace",
  last_name: "Hopper",
  email: null,
  phone: "+447911000000",
  status: "active",
};

function Wrapper({ onCreateNew }: { onCreateNew?: () => void }) {
  const [value, setValue] = useState<Guest | null>(null);
  return <GuestPicker value={value} onChange={setValue} onCreateNew={onCreateNew} />;
}

describe("GuestPicker", () => {
  it("shows search results after typing at least 2 characters", async () => {
    server.use(
      http.get("/api/v1/guests", ({ request }) => {
        const search = new URL(request.url).searchParams.get("search") ?? "";
        if (search.includes("ad")) return HttpResponse.json(drfPage([ada]));
        return HttpResponse.json(drfPage([]));
      }),
    );

    renderWithProviders(<Wrapper />);
    await userEvent.click(screen.getByRole("combobox"));
    await userEvent.type(screen.getByLabelText(/search guests/i), "ada");
    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("ada@example.com")).toBeInTheDocument();
  });

  it("only resolves ACTIVE guests — search request carries status=active", async () => {
    const seen: string[] = [];
    server.use(
      http.get("/api/v1/guests", ({ request }) => {
        seen.push(request.url);
        return HttpResponse.json(drfPage([ada]));
      }),
    );

    renderWithProviders(<Wrapper />);
    await userEvent.click(screen.getByRole("combobox"));
    await userEvent.type(screen.getByLabelText(/search guests/i), "ada");
    await screen.findByText("Ada Lovelace");

    const hit = seen.find((u) => new URL(u).searchParams.get("search") === "ada");
    expect(hit).toBeDefined();
    expect(new URL(hit!).searchParams.get("status")).toBe("active");
  });

  it("falls back to phone when a guest has no email", async () => {
    server.use(http.get("/api/v1/guests", () => HttpResponse.json(drfPage([grace]))));

    renderWithProviders(<Wrapper />);
    await userEvent.click(screen.getByRole("combobox"));
    await userEvent.type(screen.getByLabelText(/search guests/i), "gr");
    expect(await screen.findByText("Grace Hopper")).toBeInTheDocument();
    expect(screen.getByText("+447911000000")).toBeInTheDocument();
  });

  it("selects a guest and closes the popover", async () => {
    server.use(http.get("/api/v1/guests", () => HttpResponse.json(drfPage([ada, grace]))));

    renderWithProviders(<Wrapper />);
    await userEvent.click(screen.getByRole("combobox"));
    await userEvent.type(screen.getByLabelText(/search guests/i), "ad");
    await userEvent.click(await screen.findByText("Ada Lovelace"));
    await waitFor(() => expect(screen.getByRole("combobox")).toHaveTextContent("Ada Lovelace"));
  });

  it("shows empty state when no results", async () => {
    server.use(http.get("/api/v1/guests", () => HttpResponse.json(drfPage([]))));

    renderWithProviders(<Wrapper />);
    await userEvent.click(screen.getByRole("combobox"));
    await userEvent.type(screen.getByLabelText(/search guests/i), "zzz");
    expect(await screen.findByText(/no guests found/i)).toBeInTheDocument();
  });

  it("shows minimum character hint before typing enough", async () => {
    renderWithProviders(<Wrapper />);
    await userEvent.click(screen.getByRole("combobox"));
    expect(screen.getByText(/type at least 2 characters/i)).toBeInTheDocument();
  });

  it("calls onCreateNew when the create-new action is clicked", async () => {
    const onCreateNew = vi.fn();
    renderWithProviders(<Wrapper onCreateNew={onCreateNew} />);
    await userEvent.click(screen.getByRole("combobox"));
    await userEvent.click(screen.getByText(/new guest/i));
    expect(onCreateNew).toHaveBeenCalledOnce();
  });
});
