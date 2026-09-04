import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { drfPage } from "@/test/drf";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { FeatureMultiSelect } from "./FeatureMultiSelect";

const categories = [
  {
    id: 1,
    name: "Outdoor",
    slug: "outdoor",
    description: "",
    icon: "",
    sort_order: 0,
    is_active: true,
  },
  {
    id: 2,
    name: "Kitchen",
    slug: "kitchen",
    description: "",
    icon: "",
    sort_order: 1,
    is_active: true,
  },
];

const features = [
  {
    id: 10,
    category: 1,
    name: "Pool",
    slug: "pool",
    description: "",
    icon: "",
    sort_order: 0,
    is_active: true,
    service_type: "amenity",
  },
  {
    id: 11,
    category: 1,
    name: "Sea view",
    slug: "sea-view",
    description: "",
    icon: "",
    sort_order: 1,
    is_active: true,
    service_type: "amenity",
  },
  {
    id: 12,
    category: 2,
    name: "Oven",
    slug: "oven",
    description: "",
    icon: "",
    sort_order: 0,
    is_active: true,
    service_type: "amenity",
  },
];

function installFeatures() {
  server.use(
    http.get("/api/v1/feature-categories", () => HttpResponse.json(drfPage(categories))),
    http.get("/api/v1/features", () => HttpResponse.json(drfPage(features))),
  );
}

async function openPicker() {
  const trigger = await screen.findByRole("button", { name: /features/i });
  await userEvent.click(trigger);
}

describe("FeatureMultiSelect", () => {
  it("groups feature options by category", async () => {
    installFeatures();
    renderWithProviders(<FeatureMultiSelect value={[]} onChange={() => {}} />);
    await openPicker();
    expect(await screen.findByText("Outdoor")).toBeInTheDocument();
    expect(screen.getByText("Kitchen")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Pool" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Oven" })).toBeInTheDocument();
  });

  it("checking an option adds its slug", async () => {
    installFeatures();
    let picked: string[] = [];
    renderWithProviders(<FeatureMultiSelect value={[]} onChange={(v) => (picked = v)} />);
    await openPicker();
    await userEvent.click(await screen.findByRole("checkbox", { name: "Pool" }));
    expect(picked).toEqual(["pool"]);
  });

  it("unchecking a selected option removes its slug", async () => {
    installFeatures();
    let picked: string[] = ["pool", "oven"];
    renderWithProviders(
      <FeatureMultiSelect value={["pool", "oven"]} onChange={(v) => (picked = v)} />,
    );
    await openPicker();
    await userEvent.click(await screen.findByRole("checkbox", { name: "Pool" }));
    expect(picked).toEqual(["oven"]);
  });

  it("renders a chip per selected feature and removes it via the chip's remove control", async () => {
    installFeatures();
    let picked: string[] = ["pool", "oven"];
    renderWithProviders(
      <FeatureMultiSelect value={["pool", "oven"]} onChange={(v) => (picked = v)} />,
    );
    expect(await screen.findByText("Pool")).toBeInTheDocument();
    expect(screen.getByText("Oven")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /remove pool/i }));
    expect(picked).toEqual(["oven"]);
  });

  it("shows a selected-count summary on the trigger", async () => {
    installFeatures();
    renderWithProviders(<FeatureMultiSelect value={["pool", "oven"]} onChange={() => {}} />);
    expect(await screen.findByRole("button", { name: /2 features selected/i })).toBeInTheDocument();
  });
});
