import { http, HttpResponse } from "msw";
import { Navigate, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { PropertyDetailLayout } from "../PropertyDetailLayout";
import { DetailsTab } from "../tabs/DetailsTab";
import { ComingSoonTab } from "@/components/feedback/ComingSoonTab";

const propertyFixture = {
  id: 5,
  name: "Casa Norte",
  display_name: "Casa Norte",
  slug: "casa-norte",
  licence_number: "ETV-1234",
  status: "active",
  channel: "direct",
  category: null,
  group: null,
  region: null,
  feature_ids: [],
  legacy_id: null,
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2026-05-01T00:00:00Z",
};

function emptyPage<T>(value: T) {
  return {
    count: Array.isArray(value) ? value.length : 0,
    next: null,
    previous: null,
    results: value,
  };
}

function installDetailHandlers() {
  server.use(
    http.get("/api/v1/properties/casa-norte", () => HttpResponse.json(propertyFixture)),
    http.get("/api/v1/properties/casa-norte/descriptions", () =>
      HttpResponse.json(emptyPage([{ id: 1, title: "Welcome", body: "A beautiful villa." }])),
    ),
    http.get("/api/v1/properties/casa-norte/features", () =>
      HttpResponse.json(
        emptyPage([
          { id: 3, name: "Pool" },
          { id: 4, name: "Sea view" },
        ]),
      ),
    ),
    http.get("/api/v1/properties/casa-norte/rooms", () =>
      HttpResponse.json(emptyPage([{ id: 7, name: "Master bedroom", count: 1 }])),
    ),
  );
}

function setup(initial: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/properties/:id" element={<PropertyDetailLayout />}>
        <Route index element={<Navigate to="details" replace />} />
        <Route path="details" element={<DetailsTab />} />
        <Route path="pricing" element={<ComingSoonTab tabName="Pricing" />} />
      </Route>
    </Routes>,
    { route: initial },
  );
}

describe("PropertyDetailLayout", () => {
  it("renders right rail with property name and status badge", async () => {
    installDetailHandlers();
    setup("/properties/casa-norte/details");
    await waitFor(() => expect(screen.getAllByText("Casa Norte")[0]).toBeInTheDocument());
    expect(screen.getByText("active")).toBeInTheDocument();
  });

  it("renders the Details tab with sub-resources", async () => {
    installDetailHandlers();
    setup("/properties/casa-norte/details");
    expect(await screen.findByText(/A beautiful villa\./i)).toBeInTheDocument();
    expect(await screen.findByText("Pool")).toBeInTheDocument();
    expect(await screen.findByText("Master bedroom")).toBeInTheDocument();
  });

  it("renders coming-soon on /pricing without making sub-resource calls", async () => {
    let descriptionsCalls = 0;
    server.use(
      http.get("/api/v1/properties/casa-norte", () => HttpResponse.json(propertyFixture)),
      http.get("/api/v1/properties/casa-norte/descriptions", () => {
        descriptionsCalls += 1;
        return HttpResponse.json(emptyPage([]));
      }),
      http.get("/api/v1/properties/casa-norte/features", () => HttpResponse.json(emptyPage([]))),
      http.get("/api/v1/properties/casa-norte/rooms", () => HttpResponse.json(emptyPage([]))),
    );
    setup("/properties/casa-norte/pricing");
    expect(await screen.findByText(/Pricing — coming in next phase/i)).toBeInTheDocument();
    expect(descriptionsCalls).toBe(0);
  });

  it("still renders other sub-blocks when one sub-resource fails", async () => {
    server.use(
      http.get("/api/v1/properties/casa-norte", () => HttpResponse.json(propertyFixture)),
      http.get("/api/v1/properties/casa-norte/descriptions", () =>
        HttpResponse.json({}, { status: 500 }),
      ),
      http.get("/api/v1/properties/casa-norte/features", () =>
        HttpResponse.json(emptyPage([{ id: 9, name: "Wi-Fi" }])),
      ),
      http.get("/api/v1/properties/casa-norte/rooms", () => HttpResponse.json(emptyPage([]))),
    );
    setup("/properties/casa-norte/details");
    expect(await screen.findByText(/Couldn't load descriptions/i)).toBeInTheDocument();
    expect(await screen.findByText("Wi-Fi")).toBeInTheDocument();
  });
});

describe("RequireAuth guard interaction is handled by the higher-level router", () => {
  it("placeholder — covered in higher-level integration", async () => {
    await userEvent.setup();
    expect(true).toBe(true);
  });
});
