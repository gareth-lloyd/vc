import { useState } from "react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";
import { CompanyPicker } from "../components/CompanyPicker";
import type { Company } from "../schemas";

const acme: Company = {
  id: 101,
  name: "Acme Travel",
  org_type: "agency",
  status: "active",
  town: "Athens",
};

const beta: Company = {
  id: 102,
  name: "Beta Tours",
  org_type: "agency",
  status: "active",
};

function Wrapper({ onCreateNew }: { onCreateNew?: () => void }) {
  const [value, setValue] = useState<Company | null>(null);
  return <CompanyPicker value={value} onChange={setValue} onCreateNew={onCreateNew} />;
}

describe("CompanyPicker", () => {
  it("shows search results after typing at least 2 characters and scopes to agency", async () => {
    let capturedOrgType: string | null = null;
    server.use(
      http.get("/api/v1/organisations", ({ request }) => {
        const url = new URL(request.url);
        capturedOrgType = url.searchParams.get("org_type");
        const q = url.searchParams.get("search") ?? "";
        if (q.includes("acm")) return HttpResponse.json(drfPage([acme]));
        return HttpResponse.json(drfPage([]));
      }),
    );

    renderWithProviders(<Wrapper />);
    await userEvent.click(screen.getByRole("combobox"));
    await userEvent.type(screen.getByLabelText(/search companies/i), "acm");
    expect(await screen.findByText("Acme Travel")).toBeInTheDocument();
    expect(screen.getByText("Athens")).toBeInTheDocument();
    expect(capturedOrgType).toBe("agency");
  });

  it("selects a company and closes the popover", async () => {
    server.use(http.get("/api/v1/organisations", () => HttpResponse.json(drfPage([acme, beta]))));

    renderWithProviders(<Wrapper />);
    await userEvent.click(screen.getByRole("combobox"));
    await userEvent.type(screen.getByLabelText(/search companies/i), "ac");
    await userEvent.click(await screen.findByText("Acme Travel"));
    await waitFor(() => expect(screen.getByRole("combobox")).toHaveTextContent("Acme Travel"));
  });

  it("shows empty state when no results", async () => {
    server.use(http.get("/api/v1/organisations", () => HttpResponse.json(drfPage([]))));

    renderWithProviders(<Wrapper />);
    await userEvent.click(screen.getByRole("combobox"));
    await userEvent.type(screen.getByLabelText(/search companies/i), "zzz");
    expect(await screen.findByText(/no companies found/i)).toBeInTheDocument();
  });

  it("shows minimum character hint before typing enough", async () => {
    renderWithProviders(<Wrapper />);
    await userEvent.click(screen.getByRole("combobox"));
    expect(screen.getByText(/type at least 2 characters/i)).toBeInTheDocument();
  });

  it("calls onCreateNew when 'Create new company' is clicked", async () => {
    const onCreateNew = vi.fn();
    renderWithProviders(<Wrapper onCreateNew={onCreateNew} />);
    await userEvent.click(screen.getByRole("combobox"));
    await userEvent.click(screen.getByText(/create new company/i));
    expect(onCreateNew).toHaveBeenCalledOnce();
  });
});
