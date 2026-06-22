import { describe, expect, it } from "vitest";
import {
  companyCreateInputSchema,
  companySchema,
  companyWriteInputSchema,
  orgStatusSchema,
  orgTypeSchema,
} from "../schemas";

describe("orgTypeSchema", () => {
  it("accepts the three serialized org types", () => {
    expect(orgTypeSchema.parse("agency")).toBe("agency");
    expect(orgTypeSchema.parse("mgmt")).toBe("mgmt");
    expect(orgTypeSchema.parse("supplier")).toBe("supplier");
  });

  it("rejects an unknown org type", () => {
    expect(() => orgTypeSchema.parse("management_company")).toThrow();
  });
});

describe("orgStatusSchema", () => {
  it("accepts active and inactive", () => {
    expect(orgStatusSchema.parse("active")).toBe("active");
    expect(orgStatusSchema.parse("inactive")).toBe("inactive");
  });

  it("rejects an unknown status", () => {
    expect(() => orgStatusSchema.parse("archived")).toThrow();
  });
});

describe("companyWriteInputSchema", () => {
  it("accepts a company with just a name", () => {
    const result = companyWriteInputSchema.parse({ name: "Acme Travel" });
    expect(result.name).toBe("Acme Travel");
  });

  it("requires a non-empty name", () => {
    expect(() => companyWriteInputSchema.parse({})).toThrow();
    expect(() => companyWriteInputSchema.parse({ name: "" })).toThrow();
  });

  it("trims whitespace from the name", () => {
    const result = companyWriteInputSchema.parse({ name: "  Acme Travel  " });
    expect(result.name).toBe("Acme Travel");
  });

  it("rejects an invalid email when one is supplied", () => {
    expect(() => companyWriteInputSchema.parse({ name: "Acme", email: "not-an-email" })).toThrow(
      /valid email/i,
    );
  });

  it("accepts a valid email", () => {
    const result = companyWriteInputSchema.parse({ name: "Acme", email: "ops@acme.test" });
    expect(result.email).toBe("ops@acme.test");
  });
});

describe("companyCreateInputSchema", () => {
  it("requires a name (no org_type collected here)", () => {
    expect(() => companyCreateInputSchema.parse({})).toThrow();
    const result = companyCreateInputSchema.parse({ name: "Acme" });
    expect(result.name).toBe("Acme");
  });
});

describe("companySchema", () => {
  it("strips unexposed fields and parses a detail row", () => {
    const result = companySchema.parse({
      id: 3,
      name: "Acme Travel",
      org_type: "agency",
      status: "active",
      email: "ops@acme.test",
      phone: null,
      town: "Athens",
      // The backend never exposes country, but extra keys are stripped anyway.
      country: "GR",
    });
    expect(result.id).toBe(3);
    expect(result.org_type).toBe("agency");
    expect("country" in result).toBe(false);
  });
});
