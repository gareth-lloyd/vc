import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { useLocation } from "react-router-dom";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { geoLookupHandlers } from "@/test/msw/handlers";
import { renderWithProviders } from "@/test/render";
import { CreatePropertyDialog } from "../components/CreatePropertyDialog";

// Shared param-aware geo fixture (Spain/Ibiza 7, Greece/Crete 11) — the
// country picker is a picker aid, not a payload field.
function stubTaxonomies() {
  server.use(...geoLookupHandlers);
}

async function pickRegion() {
  await userEvent.click(screen.getByRole("combobox", { name: /region/i }));
  // Unscoped (no country picked) labels carry the country suffix.
  await userEvent.click(await screen.findByRole("option", { name: /^Ibiza/ }));
}

const LocationProbe = () => {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
};

describe("CreatePropertyDialog", () => {
  it("auto-derives slug + display name, posts the required fields, and navigates to the new villa", async () => {
    stubTaxonomies();
    let postBody: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/properties", async ({ request }) => {
        postBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 77, status: "draft", ...postBody }, { status: 201 });
      }),
    );

    renderWithProviders(
      <>
        <CreatePropertyDialog open onOpenChange={() => {}} />
        <LocationProbe />
      </>,
    );

    await userEvent.type(screen.getByLabelText(/^name$/i), "Villa Aurora");
    // Slug + display name are derived from the name until hand-edited.
    expect(screen.getByLabelText(/^slug$/i)).toHaveValue("villa-aurora");
    expect(screen.getByLabelText(/display name/i)).toHaveValue("Villa Aurora");

    await pickRegion();
    await userEvent.click(screen.getByRole("button", { name: /create villa/i }));

    await waitFor(() => expect(postBody).not.toBeNull());
    expect(postBody).toEqual({
      name: "Villa Aurora",
      display_name: "Villa Aurora",
      slug: "villa-aurora",
      region: 7,
    });
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/properties/77"));
  });

  it("stops deriving the slug once the operator edits it", async () => {
    stubTaxonomies();
    let postBody: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/properties", async ({ request }) => {
        postBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 9, status: "draft", ...postBody }, { status: 201 });
      }),
    );

    renderWithProviders(<CreatePropertyDialog open onOpenChange={() => {}} />);

    await userEvent.type(screen.getByLabelText(/^slug$/i), "custom-slug");
    await userEvent.type(screen.getByLabelText(/^name$/i), "Villa Aurora");
    expect(screen.getByLabelText(/^slug$/i)).toHaveValue("custom-slug");

    await pickRegion();
    await userEvent.click(screen.getByRole("button", { name: /create villa/i }));

    await waitFor(() => expect(postBody).not.toBeNull());
    expect(postBody).toEqual(expect.objectContaining({ slug: "custom-slug" }));
  });

  it("surfaces a duplicate-slug 400 as an inline field error", async () => {
    stubTaxonomies();
    server.use(
      http.post("/api/v1/properties", () =>
        HttpResponse.json(
          { field_errors: { slug: ["property with this Slug already exists."] } },
          { status: 400 },
        ),
      ),
    );

    renderWithProviders(<CreatePropertyDialog open onOpenChange={() => {}} />);

    await userEvent.type(screen.getByLabelText(/^name$/i), "Villa Aurora");
    await pickRegion();
    await userEvent.click(screen.getByRole("button", { name: /create villa/i }));

    expect(await screen.findByText(/slug already exists/i)).toBeInTheDocument();
  });

  it("narrows regions to the picked country and resets the region on change", async () => {
    stubTaxonomies();
    renderWithProviders(<CreatePropertyDialog open onOpenChange={() => {}} />);

    await userEvent.click(screen.getByRole("combobox", { name: /country/i }));
    await userEvent.click(await screen.findByRole("option", { name: "Spain" }));

    // Scoped: only Spanish regions on offer, plain labels.
    await userEvent.click(screen.getByRole("combobox", { name: /region/i }));
    expect(await screen.findByRole("option", { name: "Ibiza" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Crete/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("option", { name: "Ibiza" }));
    expect(screen.getByRole("combobox", { name: /region/i })).toHaveTextContent("Ibiza");

    // Switching country resets the region to unselected.
    await userEvent.click(screen.getByRole("combobox", { name: /country/i }));
    await userEvent.click(await screen.findByRole("option", { name: "Greece" }));
    expect(screen.getByRole("combobox", { name: /region/i })).not.toHaveTextContent("Ibiza");
  });

  it("blocks submission until the region is chosen", async () => {
    stubTaxonomies();
    let posted = false;
    server.use(
      http.post("/api/v1/properties", () => {
        posted = true;
        return HttpResponse.json({ id: 1, status: "draft" }, { status: 201 });
      }),
    );

    renderWithProviders(<CreatePropertyDialog open onOpenChange={() => {}} />);

    await userEvent.type(screen.getByLabelText(/^name$/i), "Villa Aurora");
    await userEvent.click(screen.getByRole("button", { name: /create villa/i }));

    expect(await screen.findByText(/pick a region/i)).toBeInTheDocument();
    expect(posted).toBe(false);
  });
});
