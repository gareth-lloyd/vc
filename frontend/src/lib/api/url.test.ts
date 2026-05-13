import { describe, expect, it } from "vitest";
import { buildQuery, joinUrl } from "./url";

describe("buildQuery", () => {
  it("returns empty string for empty/undefined params", () => {
    expect(buildQuery()).toBe("");
    expect(buildQuery({})).toBe("");
  });

  it("omits undefined and null values", () => {
    expect(buildQuery({ a: undefined, b: null, c: "x" })).toBe("?c=x");
  });

  it("keeps empty strings (caller's choice)", () => {
    expect(buildQuery({ q: "" })).toBe("?q=");
  });

  it("serialises arrays as repeated keys", () => {
    expect(buildQuery({ status: ["draft", "confirmed"] })).toBe("?status=draft&status=confirmed");
  });

  it("coerces numbers and booleans", () => {
    expect(buildQuery({ page: 2, active: true })).toBe("?page=2&active=true");
  });

  it("encodes special characters", () => {
    expect(buildQuery({ q: "a b&c" })).toBe("?q=a+b%26c");
  });
});

describe("joinUrl", () => {
  it("joins base + path with single slash", () => {
    expect(joinUrl("", "/api/v1/foo")).toBe("/api/v1/foo");
    expect(joinUrl("https://x.test", "/api/v1/foo")).toBe("https://x.test/api/v1/foo");
    expect(joinUrl("https://x.test/", "/api/v1/foo")).toBe("https://x.test/api/v1/foo");
    expect(joinUrl("https://x.test", "api/v1/foo")).toBe("https://x.test/api/v1/foo");
  });
});
