import { describe, expect, it } from "vitest";
import { slugify } from "./slug";

describe("slugify", () => {
  it("lowercases and replaces spaces with single dashes", () => {
    expect(slugify("Villa Aurora")).toBe("villa-aurora");
  });

  it("collapses runs of whitespace and punctuation into one dash", () => {
    expect(slugify("Villa   Aurora")).toBe("villa-aurora");
    expect(slugify("Villa --- Aurora")).toBe("villa-aurora");
    expect(slugify("Villa, Aurora & Sea")).toBe("villa-aurora-sea");
  });

  it("strips diacritics from accented characters", () => {
    expect(slugify("Casa Niça")).toBe("casa-nica");
    expect(slugify("Château Élysée")).toBe("chateau-elysee");
  });

  it("trims leading and trailing dashes", () => {
    expect(slugify("  Villa Aurora  ")).toBe("villa-aurora");
    expect(slugify("!!!Villa!!!")).toBe("villa");
  });

  it("keeps digits", () => {
    expect(slugify("Villa 23")).toBe("villa-23");
  });

  it("returns an empty string when there is nothing slug-worthy", () => {
    expect(slugify("")).toBe("");
    expect(slugify("   ")).toBe("");
    expect(slugify("—&—")).toBe("");
  });
});
