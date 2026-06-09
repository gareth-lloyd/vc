import { describe, expect, it } from "vitest";
import { isSafeNextPath } from "../useNextPath";

describe("isSafeNextPath", () => {
  it("accepts a same-origin relative path", () => {
    expect(isSafeNextPath("/contacts")).toBe(true);
    expect(isSafeNextPath("/properties/42?tab=people")).toBe(true);
  });

  it("rejects protocol-relative and absolute URLs (open-redirect vectors)", () => {
    expect(isSafeNextPath("//evil.com")).toBe(false);
    expect(isSafeNextPath("https://evil.com")).toBe(false);
    expect(isSafeNextPath("http://evil.com")).toBe(false);
  });

  it("rejects backslash tricks and non-path values", () => {
    expect(isSafeNextPath("/\\evil.com")).toBe(false);
    expect(isSafeNextPath("\\/evil.com")).toBe(false);
    expect(isSafeNextPath("contacts")).toBe(false);
    expect(isSafeNextPath("")).toBe(false);
    expect(isSafeNextPath(undefined)).toBe(false);
  });
});
