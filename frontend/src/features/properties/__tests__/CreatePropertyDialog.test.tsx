import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { useLocation } from "react-router-dom";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { drfPage } from "@/test/drf";
import { renderWithProviders } from "@/test/render";
import { CreatePropertyDialog } from "../components/CreatePropertyDialog";

function stubTaxonomies() {
  server.use(
    http.get("/api/v1/property-categories", () =>
      HttpResponse.json(drfPage([{ id: 1, name: "Villa", slug: "villa", is_active: true }])),
    ),
    http.get("/api/v1/property-groups", () =>
      HttpResponse.json(drfPage([{ id: 2, name: "Portfolio A", is_active: true }])),
    ),
    http.get("/api/v1/regions", () =>
      HttpResponse.json(
        drfPage([{ id: 3, name: "Tuscany", slug: "tuscany", country: null, is_active: true }]),
      ),
    ),
  );
}

async function pickFks() {
  await userEvent.click(screen.getByRole("combobox", { name: /category/i }));
  await userEvent.click(await screen.findByRole("option", { name: "Villa" }));
  await userEvent.click(screen.getByRole("combobox", { name: /group/i }));
  await userEvent.click(await screen.findByRole("option", { name: "Portfolio A" }));
  await userEvent.click(screen.getByRole("combobox", { name: /region/i }));
  await userEvent.click(await screen.findByRole("option", { name: "Tuscany" }));
}

const LocationProbe = () => {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
};

describe("CreatePropertyDialog", () => {
  it("auto-derives slug + display name, posts the six fields, and navigates to the new villa", async () => {
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

    await pickFks();
    await userEvent.click(screen.getByRole("button", { name: /create villa/i }));

    await waitFor(() => expect(postBody).not.toBeNull());
    expect(postBody).toEqual({
      name: "Villa Aurora",
      display_name: "Villa Aurora",
      slug: "villa-aurora",
      category: 1,
      group: 2,
      region: 3,
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

    await pickFks();
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
    await pickFks();
    await userEvent.click(screen.getByRole("button", { name: /create villa/i }));

    expect(await screen.findByText(/slug already exists/i)).toBeInTheDocument();
  });

  it("blocks submission until the required FKs are chosen", async () => {
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

    expect(await screen.findByText(/pick a category/i)).toBeInTheDocument();
    expect(posted).toBe(false);
  });
});
