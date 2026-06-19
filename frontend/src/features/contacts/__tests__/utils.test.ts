import { describe, expect, it } from "vitest";
import type { Contact } from "../schemas";
import { primaryEmail, primaryPhone } from "../utils";

function contact(overrides: Partial<Contact>): Contact {
  return {
    id: 1,
    first_name: "Ada",
    last_name: "Lovelace",
    emails: [],
    phones: [],
    ...overrides,
  };
}

describe("primaryEmail", () => {
  it("returns the primary email when one is flagged", () => {
    const c = contact({
      emails: [
        { id: 1, email: "first@example.com" },
        { id: 2, email: "primary@example.com", is_primary: true },
      ],
    });
    expect(primaryEmail(c)).toBe("primary@example.com");
  });

  it("falls back to the first email when none is flagged primary", () => {
    const c = contact({ emails: [{ id: 1, email: "first@example.com" }] });
    expect(primaryEmail(c)).toBe("first@example.com");
  });

  it("returns an empty string when there are no emails", () => {
    expect(primaryEmail(contact({ emails: [] }))).toBe("");
  });
});

describe("primaryPhone", () => {
  it("returns the primary phone when one is flagged", () => {
    const c = contact({
      phones: [
        { id: 1, number: "+1" },
        { id: 2, number: "+2", is_primary: true },
      ],
    });
    expect(primaryPhone(c)).toBe("+2");
  });

  it("falls back to the first phone when none is flagged primary", () => {
    const c = contact({ phones: [{ id: 1, number: "+1" }] });
    expect(primaryPhone(c)).toBe("+1");
  });

  it("returns an empty string when there are no phones", () => {
    expect(primaryPhone(contact({ phones: [] }))).toBe("");
  });
});
