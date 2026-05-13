import { describe, expect, it } from "vitest";
import {
  contactEmailWriteInputSchema,
  contactPhoneWriteInputSchema,
  contactWriteInputSchema,
} from "../schemas";

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
