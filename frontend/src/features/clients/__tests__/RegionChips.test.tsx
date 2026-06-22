import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";
import { RegionChips } from "../RegionChips";

const regions = [
  { id: 7, country: 1, name: "Tuscany", slug: "tuscany" },
  { id: 9, country: 1, name: "Amalfi Coast", slug: "amalfi" },
];

describe("RegionChips", () => {
  it("labels known slugs with their region name", async () => {
    server.use(http.get("/api/v1/regions", () => HttpResponse.json(drfPage(regions))));
    renderWithProviders(<RegionChips slugs={["tuscany", "amalfi"]} />);
    expect(await screen.findByText("Amalfi Coast")).toBeInTheDocument();
    expect(screen.getByText("Tuscany")).toBeInTheDocument();
  });

  it("falls back to the raw slug when the region is unknown", async () => {
    server.use(http.get("/api/v1/regions", () => HttpResponse.json(drfPage(regions))));
    renderWithProviders(<RegionChips slugs={["mystery-place"]} />);
    expect(await screen.findByText("mystery-place")).toBeInTheDocument();
  });

  it("renders a dash for an empty slug list", () => {
    server.use(http.get("/api/v1/regions", () => HttpResponse.json(drfPage(regions))));
    renderWithProviders(<RegionChips slugs={[]} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
