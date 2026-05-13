import { describe, expect, it } from "vitest";
import {
  contactEmailWriteInputSchema,
  contactPhoneWriteInputSchema,
  contactWriteInputSchema,
  propertyContactAssignmentWriteInputSchema,
  propertyDetailSchema,
  propertyListItemSchema,
  propertyListResponseSchema,
} from "../schemas";

describe("propertyListItemSchema", () => {
  it("parses a minimal list payload", () => {
    expect(
      propertyListItemSchema.parse({
        id: 1,
        name: "Casa Norte",
        status: "active",
      }),
    ).toMatchObject({ id: 1, name: "Casa Norte" });
  });
});

describe("propertyListResponseSchema", () => {
  it("parses a paginated wrapper", () => {
    const parsed = propertyListResponseSchema.parse({
      count: 2,
      next: null,
      previous: null,
      results: [
        { id: 1, name: "A", status: "active" },
        { id: 2, name: "B", status: "draft" },
      ],
    });
    expect(parsed.results).toHaveLength(2);
  });
});

describe("propertyDetailSchema", () => {
  it("defaults feature_ids when omitted", () => {
    const parsed = propertyDetailSchema.parse({
      id: 5,
      name: "Villa Azul",
      status: "active",
    });
    expect(parsed.feature_ids).toEqual([]);
  });
});

describe("propertyContactAssignmentWriteInputSchema", () => {
  it("accepts a valid assignment input", () => {
    const result = propertyContactAssignmentWriteInputSchema.parse({
      contact: 1,
      role: "owner",
      start_date: "2024-01-01",
      is_primary: true,
    });
    expect(result.contact).toBe(1);
  });

  it("rejects non-integer contact id", () => {
    expect(() => propertyContactAssignmentWriteInputSchema.parse({ contact: 1.5 })).toThrow();
  });

  it("trims and enforces max-length on role", () => {
    const result = propertyContactAssignmentWriteInputSchema.parse({
      contact: 1,
      role: "  owner  ",
    });
    expect(result.role).toBe("owner");

    expect(() =>
      propertyContactAssignmentWriteInputSchema.parse({ contact: 1, role: "x".repeat(121) }),
    ).toThrow();
  });
});

describe("contactEmailWriteInputSchema", () => {
  it("accepts a valid email", () => {
    const result = contactEmailWriteInputSchema.parse({
      email: "test@example.com",
      label: "work",
    });
    expect(result.email).toBe("test@example.com");
  });

  it("rejects an invalid email", () => {
    expect(() => contactEmailWriteInputSchema.parse({ email: "not-an-email" })).toThrow(
      /valid email/i,
    );
  });

  it("enforces max-length on email", () => {
    expect(() =>
      contactEmailWriteInputSchema.parse({ email: `${"a".repeat(250)}@test.com` }),
    ).toThrow();
  });
});

describe("contactPhoneWriteInputSchema", () => {
  it("accepts a valid phone", () => {
    const result = contactPhoneWriteInputSchema.parse({ number: "+34 600 123 456" });
    expect(result.number).toBe("+34 600 123 456");
  });

  it("rejects empty phone number", () => {
    expect(() => contactPhoneWriteInputSchema.parse({ number: "" })).toThrow(/required/i);
  });

  it("enforces max-length on number", () => {
    expect(() => contactPhoneWriteInputSchema.parse({ number: "1".repeat(41) })).toThrow();
  });
});

describe("contactWriteInputSchema", () => {
  it("accepts a contact with first_name only", () => {
    const result = contactWriteInputSchema.parse({ first_name: "Alice" });
    expect(result.first_name).toBe("Alice");
  });

  it("accepts a contact with company only", () => {
    const result = contactWriteInputSchema.parse({ company: "Acme Ltd" });
    expect(result.company).toBe("Acme Ltd");
  });

  it("rejects a contact with no name or company", () => {
    expect(() => contactWriteInputSchema.parse({})).toThrow(/name or company/i);
  });

  it("trims whitespace from fields", () => {
    const result = contactWriteInputSchema.parse({ first_name: "  Alice  " });
    expect(result.first_name).toBe("Alice");
  });
});
