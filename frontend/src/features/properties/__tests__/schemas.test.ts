import { describe, expect, it } from "vitest";
import {
  PROPERTY_CONTACT_ROLES,
  ROOM_FLOORS,
  ROOM_PLACEMENTS,
  availabilityBlockWriteInputSchema,
  availabilityCellSchema,
  propertyContactAssignmentWriteInputSchema,
  propertyCreateInputSchema,
  propertyDetailSchema,
  propertyListItemSchema,
  propertyListResponseSchema,
  propertyRoomSchema,
  propertyRoomWriteInputSchema,
  propertySettingsWriteInputSchema,
  ratePeriodWriteInputSchema,
  rateBandWriteInputSchema,
  roomAttributeSchema,
  roomAttributesResponseSchema,
} from "../schemas";

describe("propertyListItemSchema — GAP-034 calendar source", () => {
  const base = { id: 1, name: "Villa", status: "active" };

  it("defaults has_active_ical_feed to false when omitted (older fixtures)", () => {
    const row = propertyListItemSchema.parse(base);
    expect(row.has_active_ical_feed).toBe(false);
    expect(row.calendar_url).toBeUndefined();
  });

  it("carries the flag and calendar_url when present, on list and detail", () => {
    const payload = {
      ...base,
      has_active_ical_feed: true,
      calendar_url: "https://o.example.com/c",
    };
    expect(propertyListItemSchema.parse(payload).has_active_ical_feed).toBe(true);
    expect(propertyDetailSchema.parse(payload).calendar_url).toBe("https://o.example.com/c");
  });

  it("accepts a null calendar_url (BE emits null when unset)", () => {
    expect(propertyListItemSchema.parse({ ...base, calendar_url: null }).calendar_url).toBeNull();
  });
});

describe("propertySettingsWriteInputSchema — GAP-034 calendar_url", () => {
  const field = propertySettingsWriteInputSchema.shape.calendar_url;

  it("accepts an empty string, a URL, null, and undefined (format is validated server-side)", () => {
    // The client only constrains the shape; Django's URLField is the authority
    // on URL *format*, and the OperationalForm surfaces its 400 in the alert.
    expect(field.safeParse("").success).toBe(true);
    expect(field.safeParse("https://owner.example.com/calendar").success).toBe(true);
    expect(field.safeParse(null).success).toBe(true);
    expect(field.safeParse(undefined).success).toBe(true);
  });
});

describe("availabilityCellSchema", () => {
  it("parses a whole-day cell without segments", () => {
    const cell = availabilityCellSchema.parse({
      date: "2026-06-01",
      available: false,
      reason: "owner_block",
      block_id: 7,
    });
    expect(cell.segments).toBeUndefined();
    expect(cell.block_id).toBe(7);
  });

  it("parses a split changeover cell with am/pm segments", () => {
    const cell = availabilityCellSchema.parse({
      date: "2026-06-08",
      available: false,
      reason: "booked",
      block_id: null,
      segments: {
        am: { available: false, reason: "booked", block_id: null },
        pm: { available: false, reason: "owner_block", block_id: 9 },
      },
    });
    expect(cell.segments?.am.reason).toBe("booked");
    expect(cell.segments?.pm.block_id).toBe(9);
  });
});

describe("propertyCreateInputSchema", () => {
  const valid = {
    name: "Villa Aurora",
    display_name: "Villa Aurora",
    slug: "villa-aurora",
    category: 1,
    region: 3,
  };

  it("accepts the five required fields", () => {
    expect(propertyCreateInputSchema.parse(valid)).toMatchObject(valid);
  });

  it("rejects a blank name", () => {
    const result = propertyCreateInputSchema.safeParse({ ...valid, name: "  " });
    expect(result.success).toBe(false);
  });

  it("rejects an unselected FK (the 0 sentinel)", () => {
    for (const field of ["category", "region"] as const) {
      const result = propertyCreateInputSchema.safeParse({ ...valid, [field]: 0 });
      expect(result.success, field).toBe(false);
    }
  });

  it("rejects a slug with invalid characters", () => {
    const result = propertyCreateInputSchema.safeParse({ ...valid, slug: "Villa Aurora!" });
    expect(result.success).toBe(false);
  });

  it("accepts a slug with digits and dashes", () => {
    expect(propertyCreateInputSchema.parse({ ...valid, slug: "villa-23-aurora" }).slug).toBe(
      "villa-23-aurora",
    );
  });
});

describe("availabilityBlockWriteInputSchema", () => {
  it("rejects a non-editable reason", () => {
    const result = availabilityBlockWriteInputSchema.safeParse({
      reason: "quotation_open",
      date_from: "2026-06-01",
      date_to: "2026-06-05",
    });
    expect(result.success).toBe(false);
  });

  it("rejects date_to <= date_from", () => {
    const result = availabilityBlockWriteInputSchema.safeParse({
      reason: "manual",
      date_from: "2026-06-05",
      date_to: "2026-06-05",
    });
    expect(result.success).toBe(false);
  });

  it("accepts a valid manual block", () => {
    const result = availabilityBlockWriteInputSchema.safeParse({
      reason: "manual",
      date_from: "2026-06-01",
      date_to: "2026-06-05",
      notes: "Owner stay",
    });
    expect(result.success).toBe(true);
  });
});

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

  it("accepts every allowed role", () => {
    for (const role of PROPERTY_CONTACT_ROLES) {
      const result = propertyContactAssignmentWriteInputSchema.parse({ contact: 1, role });
      expect(result.role).toBe(role);
    }
  });

  it("includes the legacy-reconciled roles villa_admin + management_company (GAP-048)", () => {
    // L2-1 added these to the backend ContactRole enum (reconciling legacy
    // VillaRoles 3 & 5); the FE picker must offer them too.
    expect(PROPERTY_CONTACT_ROLES).toContain("villa_admin");
    expect(PROPERTY_CONTACT_ROLES).toContain("management_company");
    for (const role of ["villa_admin", "management_company"] as const) {
      expect(propertyContactAssignmentWriteInputSchema.parse({ contact: 1, role }).role).toBe(role);
    }
  });

  it("requires role and rejects values outside the enum", () => {
    expect(() => propertyContactAssignmentWriteInputSchema.parse({ contact: 1 })).toThrow();
    expect(() =>
      propertyContactAssignmentWriteInputSchema.parse({ contact: 1, role: "cleaner" }),
    ).toThrow();
    expect(() =>
      propertyContactAssignmentWriteInputSchema.parse({ contact: 1, role: "" }),
    ).toThrow();
  });
});

describe("ratePeriodWriteInputSchema", () => {
  // GAP-056: the period owns the dates + nullable min/max-nights.
  // GAP-059: the operator label is compulsory.
  const valid = { name: "Peak", date_from: "2026-06-01", date_to: "2026-06-30" };

  it("accepts a named period", () => {
    const result = ratePeriodWriteInputSchema.parse(valid);
    expect(result.name).toBe("Peak");
    expect(result.date_from).toBe("2026-06-01");
    expect(result.date_to).toBe("2026-06-30");
  });

  it.each(["", "   "])("rejects a blank name (%j) with the i18n key (GAP-059)", (name) => {
    const result = ratePeriodWriteInputSchema.safeParse({ ...valid, name });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0]?.message).toBe("properties:errors.rate_period_name_required");
    }
  });

  it("rejects a missing name (GAP-059)", () => {
    expect(
      ratePeriodWriteInputSchema.safeParse({ date_from: "2026-06-01", date_to: "2026-06-30" })
        .success,
    ).toBe(false);
  });

  it("requires both dates", () => {
    expect(() => ratePeriodWriteInputSchema.parse({ ...valid, date_from: "" })).toThrow();
    expect(() => ratePeriodWriteInputSchema.parse({ ...valid, date_to: "" })).toThrow();
  });

  it("treats dates as inclusive — a single-day period (date_to === date_from) is valid", () => {
    expect(
      ratePeriodWriteInputSchema.parse({ ...valid, date_from: "2026-06-01", date_to: "2026-06-01" })
        .date_to,
    ).toBe("2026-06-01");
  });

  it("rejects date_to before date_from", () => {
    expect(() =>
      ratePeriodWriteInputSchema.parse({
        ...valid,
        date_from: "2026-06-30",
        date_to: "2026-06-01",
      }),
    ).toThrow();
  });

  it("rejects max_nights below min_nights but allows null", () => {
    expect(() =>
      ratePeriodWriteInputSchema.parse({ ...valid, min_nights: 3, max_nights: 2 }),
    ).toThrow();
    expect(
      ratePeriodWriteInputSchema.parse({ ...valid, min_nights: 3, max_nights: null }).max_nights,
    ).toBeNull();
    expect(
      ratePeriodWriteInputSchema.parse({ ...valid, min_nights: 3, max_nights: 3 }).max_nights,
    ).toBe(3);
  });

  it("rejects nights below 1", () => {
    expect(() => ratePeriodWriteInputSchema.parse({ ...valid, min_nights: 0 })).toThrow();
  });
});

describe("rateBandWriteInputSchema", () => {
  // GAP-056: a band is party × price only — dates live on the parent period.
  const valid = {
    min_party: 1,
    max_party: 8,
    nightly: "150.00",
    weekly: "",
    is_poa: false,
  };

  it("accepts a priced rule", () => {
    expect(rateBandWriteInputSchema.parse(valid).nightly).toBe("150.00");
  });

  it("requires min_party <= max_party", () => {
    expect(() => rateBandWriteInputSchema.parse({ ...valid, min_party: 9 })).toThrow();
    expect(rateBandWriteInputSchema.parse({ ...valid, min_party: 8 }).min_party).toBe(8);
  });

  it("requires a price unless POA", () => {
    expect(() => rateBandWriteInputSchema.parse({ ...valid, nightly: "", weekly: "" })).toThrow();
    expect(
      rateBandWriteInputSchema.parse({ ...valid, nightly: "", weekly: "", is_poa: true }).is_poa,
    ).toBe(true);
    expect(rateBandWriteInputSchema.parse({ ...valid, nightly: "", weekly: "900" }).weekly).toBe(
      "900",
    );
  });

  it("accepts a POA rule with lingering price text (payload nulls it at submit)", () => {
    expect(rateBandWriteInputSchema.parse({ ...valid, is_poa: true }).is_poa).toBe(true);
    // Even malformed leftovers in the disabled inputs must not block a POA save.
    expect(
      rateBandWriteInputSchema.parse({ ...valid, is_poa: true, nightly: "12.345" }).is_poa,
    ).toBe(true);
  });

  it("treats whitespace-only prices as empty", () => {
    expect(rateBandWriteInputSchema.parse({ ...valid, nightly: " ", weekly: "900" }).nightly).toBe(
      "",
    );
    expect(() => rateBandWriteInputSchema.parse({ ...valid, nightly: " ", weekly: "" })).toThrow();
  });

  it("validates money strings", () => {
    expect(() => rateBandWriteInputSchema.parse({ ...valid, nightly: "12,50" })).toThrow();
    expect(() => rateBandWriteInputSchema.parse({ ...valid, nightly: "12.345" })).toThrow();
    expect(() => rateBandWriteInputSchema.parse({ ...valid, nightly: "-5" })).toThrow();
    expect(rateBandWriteInputSchema.parse({ ...valid, nightly: "1250" }).nightly).toBe("1250");
    expect(rateBandWriteInputSchema.parse({ ...valid, nightly: "12.5" }).nightly).toBe("12.5");
  });
});

describe("propertyRoomSchema — GAP-064 facets + amenity links", () => {
  const base = {
    id: 200,
    property: 7,
    name: "Master",
    placement: "main_house",
    is_ensuite: true,
    sort_order: 0,
  };

  it("defaults the new fields when omitted (older fixtures)", () => {
    const room = propertyRoomSchema.parse(base);
    expect(room.ensuite_type).toBe("");
    expect(room.access).toBe("");
    expect(room.attribute_links).toEqual([]);
  });

  it("parses facets and attribute_links (read shape)", () => {
    const room = propertyRoomSchema.parse({
      ...base,
      ensuite_type: "both",
      access: "outside",
      attribute_links: [
        {
          id: 90,
          attribute: 3,
          slug: "fireplace",
          name: "Fireplace",
          icon: "flame",
          is_active: false,
          note: "gas",
        },
      ],
    });
    expect(room.ensuite_type).toBe("both");
    expect(room.access).toBe("outside");
    expect(room.attribute_links[0]).toMatchObject({
      attribute: 3,
      name: "Fireplace",
      is_active: false,
      note: "gas",
    });
  });
});

describe("propertyRoomSchema — GAP-065 location axes", () => {
  const base = {
    id: 201,
    property: 7,
    name: "Loft",
    is_ensuite: false,
    sort_order: 1,
  };

  it("defaults placement, floor and placement_note when omitted (older fixtures)", () => {
    const room = propertyRoomSchema.parse(base);
    expect(room.placement).toBe("");
    expect(room.floor).toBe("");
    expect(room.placement_note).toBe("");
  });

  it("accepts blank placement and floor ('' = unknown)", () => {
    const room = propertyRoomSchema.parse({ ...base, placement: "", floor: "" });
    expect(room.placement).toBe("");
    expect(room.floor).toBe("");
  });

  it("parses the new building members and every floor rung", () => {
    for (const placement of ["cottage", "bungalow", "studio"] as const) {
      expect(ROOM_PLACEMENTS).toContain(placement);
      expect(propertyRoomSchema.parse({ ...base, placement }).placement).toBe(placement);
    }
    for (const floor of ROOM_FLOORS) {
      expect(propertyRoomSchema.parse({ ...base, floor }).floor).toBe(floor);
    }
  });

  it("carries the preserved legacy placement_note (read shape)", () => {
    const room = propertyRoomSchema.parse({
      ...base,
      placement: "guest_house",
      floor: "first",
      placement_note: "First floor of the guest house",
    });
    expect(room.placement_note).toBe("First floor of the guest house");
  });

  it("rejects junk placement and floor", () => {
    expect(() => propertyRoomSchema.parse({ ...base, placement: "treehouse" })).toThrow();
    expect(() => propertyRoomSchema.parse({ ...base, floor: "mezzanine" })).toThrow();
  });
});

describe("roomAttributeSchema — GAP-064 catalog", () => {
  it("parses a catalog row inside the DRF envelope", () => {
    const page = roomAttributesResponseSchema.parse({
      count: 1,
      next: null,
      previous: null,
      results: [
        {
          id: 1,
          slug: "wardrobe",
          name: "Wardrobe",
          description: "",
          icon: "shirt",
          sort_order: 1,
          is_active: true,
          implies_property_feature: null,
        },
      ],
    });
    expect(page.results[0].slug).toBe("wardrobe");
  });

  it("accepts inactive rows (the endpoint serves retired attributes too)", () => {
    const row = roomAttributeSchema.parse({
      id: 3,
      slug: "fireplace",
      name: "Fireplace",
      description: null,
      icon: null,
      sort_order: 3,
      is_active: false,
      implies_property_feature: 12,
    });
    expect(row.is_active).toBe(false);
  });
});

describe("propertyRoomWriteInputSchema", () => {
  const beds = {
    double: 1,
    twin_double: 0,
    twin: 0,
    single: 0,
    bunk: 0,
    sofa: 0,
    childrens: 0,
  };
  const valid = {
    name: "Master",
    placement: "main_house" as const,
    floor: "" as const,
    website_description: "",
    vc_notes: "",
    is_ensuite: true,
    ensuite_type: "" as const,
    access: "" as const,
    beds,
  };

  it("accepts a fully specified room", () => {
    const result = propertyRoomWriteInputSchema.parse(valid);
    expect(result.beds).toEqual(beds);
  });

  it("saves a room with just a name (beds omitted, GAP-024)", () => {
    const result = propertyRoomWriteInputSchema.parse({
      name: "Master",
      placement: "main_house" as const,
      floor: "",
      website_description: "",
      vc_notes: "",
      is_ensuite: true,
      ensuite_type: "",
      access: "",
    });
    expect(result.beds).toBeUndefined();
    expect(result.name).toBe("Master");
  });

  it("accepts blank and enum values for placement and floor, rejects junk (GAP-065)", () => {
    expect(propertyRoomWriteInputSchema.parse({ ...valid, placement: "" }).placement).toBe("");
    expect(propertyRoomWriteInputSchema.parse(valid).floor).toBe("");
    const set = propertyRoomWriteInputSchema.parse({
      ...valid,
      placement: "cottage",
      floor: "third_plus",
    });
    expect(set.placement).toBe("cottage");
    expect(set.floor).toBe("third_plus");
    expect(() =>
      propertyRoomWriteInputSchema.parse({ ...valid, placement: "treehouse" }),
    ).toThrow();
    expect(() => propertyRoomWriteInputSchema.parse({ ...valid, floor: "mezzanine" })).toThrow();
  });

  it("keeps placement/floor required so a PATCH can send '' to clear them (GAP-065)", () => {
    // Same clearing-trap posture as the GAP-064 facets: `.optional()` would
    // omit the field and silently stop clearing a previously-set value.
    expect(() => propertyRoomWriteInputSchema.parse({ ...valid, placement: undefined })).toThrow();
    expect(() => propertyRoomWriteInputSchema.parse({ ...valid, floor: undefined })).toThrow();
  });

  it("strips placement_note — the form must never write it (GAP-065)", () => {
    const result = propertyRoomWriteInputSchema.parse({
      ...valid,
      placement_note: "First floor of the guest house",
    });
    expect("placement_note" in result).toBe(false);
  });

  it("accepts blank and enum values for the GAP-064 facets, rejects junk", () => {
    expect(propertyRoomWriteInputSchema.parse(valid).ensuite_type).toBe("");
    expect(propertyRoomWriteInputSchema.parse(valid).access).toBe("");
    const set = propertyRoomWriteInputSchema.parse({
      ...valid,
      ensuite_type: "shower",
      access: "outside",
    });
    expect(set.ensuite_type).toBe("shower");
    expect(set.access).toBe("outside");
    expect(() => propertyRoomWriteInputSchema.parse({ ...valid, ensuite_type: "sauna" })).toThrow();
    expect(() => propertyRoomWriteInputSchema.parse({ ...valid, access: "teleport" })).toThrow();
  });

  it("keeps the facets required so a PATCH can send '' to clear them", () => {
    // Same clearing-trap guard as website_description: `.optional()` would omit
    // the field and silently stop clearing a previously-set value.
    expect(() =>
      propertyRoomWriteInputSchema.parse({ ...valid, ensuite_type: undefined }),
    ).toThrow();
    expect(() => propertyRoomWriteInputSchema.parse({ ...valid, access: undefined })).toThrow();
  });

  it("keeps attribute_links optional (absent ≠ clear) but validates entries", () => {
    expect(propertyRoomWriteInputSchema.parse(valid).attribute_links).toBeUndefined();
    const result = propertyRoomWriteInputSchema.parse({
      ...valid,
      attribute_links: [{ attribute: 3, note: "walk-in" }, { attribute: 5 }],
    });
    expect(result.attribute_links).toEqual([{ attribute: 3, note: "walk-in" }, { attribute: 5 }]);
    expect(() =>
      propertyRoomWriteInputSchema.parse({ ...valid, attribute_links: [{ note: "no pk" }] }),
    ).toThrow();
  });

  it("still rejects a blank name", () => {
    expect(() => propertyRoomWriteInputSchema.parse({ ...valid, name: "  " })).toThrow();
  });

  it("keeps empty description/notes as '' so a PATCH can clear them", () => {
    // Regression guard: these must stay `z.string()` (not `.optional()`), or an
    // empty value would be omitted from the payload and silently stop clearing.
    const result = propertyRoomWriteInputSchema.parse(valid);
    expect(result.website_description).toBe("");
    expect(result.vc_notes).toBe("");
    // `undefined` is rejected (the field is required), proving it is NOT optional.
    expect(() =>
      propertyRoomWriteInputSchema.parse({ ...valid, website_description: undefined }),
    ).toThrow();
  });
});
