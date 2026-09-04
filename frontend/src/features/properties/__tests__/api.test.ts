import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { drfPage } from "@/test/drf";
import { server } from "@/test/msw/server";
import { fetchProperties } from "../api";
import type { PropertyFilters } from "../schemas";

afterEach(() => server.resetHandlers());

describe("fetchProperties", () => {
  it("sends `features` as a single comma-joined param, not repeated keys", async () => {
    let receivedUrl: URL | null = null;
    server.use(
      http.get("/api/v1/properties", ({ request }) => {
        receivedUrl = new URL(request.url);
        return HttpResponse.json(drfPage([]));
      }),
    );
    const filters: PropertyFilters = { features: ["pool", "sea-view"] };
    await fetchProperties(filters);

    // `URLSearchParams.get` on a repeated key silently returns only the
    // first — asserting `getAll().length === 1` catches the regression where
    // `features` is sent as an array (`?features=pool&features=sea-view`)
    // instead of one CSV value (BUG-019 U4's `toFeaturesParam` contract).
    expect(receivedUrl).not.toBeNull();
    const params = (receivedUrl as unknown as URL).searchParams;
    expect(params.getAll("features")).toEqual(["pool,sea-view"]);
  });

  it("omits `features` entirely when no features are selected", async () => {
    let receivedUrl: URL | null = null;
    server.use(
      http.get("/api/v1/properties", ({ request }) => {
        receivedUrl = new URL(request.url);
        return HttpResponse.json(drfPage([]));
      }),
    );
    await fetchProperties({});

    expect(receivedUrl).not.toBeNull();
    expect((receivedUrl as unknown as URL).searchParams.has("features")).toBe(false);
  });
});
