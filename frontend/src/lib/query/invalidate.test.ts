import { afterEach, describe, expect, it, vi } from "vitest";
import { QueryClient } from "@tanstack/react-query";
import { invalidatedKeys } from "@/test/invalidation";
import { queryKeys } from "./keys";
import {
  invalidateBookingDependents,
  invalidateContactSubtree,
  invalidateEnquiryDependents,
  invalidatePropertyAvailability,
  invalidateQuotationDependents,
  invalidateQuotationRelated,
} from "./invalidate";

function spyClient() {
  const qc = new QueryClient();
  const spy = vi.spyOn(qc, "invalidateQueries");
  const keys = () => invalidatedKeys(spy);
  return { qc, keys };
}

afterEach(() => vi.restoreAllMocks());

describe("invalidatePropertyAvailability", () => {
  it("invalidates the property's availability, holds and bookings roots plus the cross-property availability tree", () => {
    const { qc, keys } = spyClient();

    invalidatePropertyAvailability(qc, 12);

    expect(keys()).toContainEqual(queryKeys.properties.availabilityRoot(12));
    expect(keys()).toContainEqual(queryKeys.properties.holdsRoot(12));
    expect(keys()).toContainEqual(queryKeys.properties.bookingsRoot(12));
    expect(keys()).toContainEqual(queryKeys.availability.all());
  });
});

describe("invalidateContactSubtree", () => {
  it("targets the precise contact detail subtree when the id is known", () => {
    const { qc, keys } = spyClient();

    invalidateContactSubtree(qc, 7);

    expect(keys()).toContainEqual(queryKeys.contacts.detail(7));
    expect(keys()).not.toContainEqual(queryKeys.contacts.details());
  });

  it("falls back to the broad contacts detail prefix when the payload carries no contact FK", () => {
    const { qc, keys } = spyClient();

    invalidateContactSubtree(qc, undefined);

    expect(keys()).toContainEqual(queryKeys.contacts.details());
  });

  it("skips entirely when the entity is known to have no linked contact (null)", () => {
    const { qc, keys } = spyClient();

    invalidateContactSubtree(qc, null);

    expect(keys()).toEqual([]);
  });
});

describe("invalidateBookingDependents", () => {
  it("invalidates lists, status counts, dashboard, the owning property's availability and the broad contacts prefix", () => {
    const { qc, keys } = spyClient();

    invalidateBookingDependents(qc, { property: 12 });

    expect(keys()).toContainEqual(queryKeys.bookings.lists());
    expect(keys()).toContainEqual(queryKeys.bookings.statusCountsAll());
    expect(keys()).toContainEqual(queryKeys.dashboard.all());
    expect(keys()).toContainEqual(queryKeys.properties.availabilityRoot(12));
    expect(keys()).toContainEqual(queryKeys.properties.holdsRoot(12));
    expect(keys()).toContainEqual(queryKeys.properties.bookingsRoot(12));
    expect(keys()).toContainEqual(queryKeys.availability.all());
    expect(keys()).toContainEqual(queryKeys.contacts.details());
  });

  it("never invalidates a booking detail key — success handlers own it via setQueryData", () => {
    const { qc, keys } = spyClient();

    invalidateBookingDependents(qc, { property: 12 });

    expect(keys()).not.toContainEqual(queryKeys.bookings.detail(51));
    expect(keys()).not.toContainEqual(queryKeys.bookings.all());
  });

  it("skips property availability when no property id is available (money mutations)", () => {
    const { qc, keys } = spyClient();

    invalidateBookingDependents(qc);

    expect(keys()).toContainEqual(queryKeys.bookings.lists());
    expect(keys()).not.toContainEqual(queryKeys.properties.availabilityRoot(12));
    expect(keys()).not.toContainEqual(queryKeys.availability.all());
  });
});

describe("invalidateEnquiryDependents", () => {
  it("invalidates lists, status counts, dashboard and the linked person's and agent's contact subtrees", () => {
    const { qc, keys } = spyClient();

    invalidateEnquiryDependents(qc, { person: 7, agent: 9 });

    expect(keys()).toContainEqual(queryKeys.enquiries.lists());
    expect(keys()).toContainEqual(queryKeys.enquiries.statusCountsAll());
    expect(keys()).toContainEqual(queryKeys.dashboard.all());
    expect(keys()).toContainEqual(queryKeys.contacts.detail(7));
    expect(keys()).toContainEqual(queryKeys.contacts.detail(9));
  });

  it("skips contact invalidation when the enquiry has no linked person or agent", () => {
    const { qc, keys } = spyClient();

    invalidateEnquiryDependents(qc, { person: null, agent: null });

    expect(keys()).not.toContainEqual(queryKeys.contacts.detail(7));
    expect(keys()).not.toContainEqual(queryKeys.contacts.details());
  });
});

describe("invalidateQuotationRelated", () => {
  it("invalidates the parent enquiry detail subtree and both guest and agent contact subtrees", () => {
    const { qc, keys } = spyClient();

    invalidateQuotationRelated(qc, { enquiry: 8, guest: 7, agent: 9 });

    // detail(8) is a prefix of the enquiry's activity/notes sub-keys, so the
    // whole enquiry subtree is covered by this one invalidation.
    expect(keys()).toContainEqual(queryKeys.enquiries.detail(8));
    expect(keys()).toContainEqual(queryKeys.contacts.detail(7));
    expect(keys()).toContainEqual(queryKeys.contacts.detail(9));
  });

  it("skips enquiry and contact keys when the quotation has none linked", () => {
    const { qc, keys } = spyClient();

    invalidateQuotationRelated(qc, { enquiry: null, guest: null, agent: null });

    expect(keys()).toEqual([]);
  });
});

describe("invalidateQuotationDependents", () => {
  it("invalidates the quotation's own detail, lists and status counts plus the related enquiry/contacts", () => {
    const { qc, keys } = spyClient();

    invalidateQuotationDependents(qc, { id: 4, enquiry: 8, guest: 7, agent: null });

    expect(keys()).toContainEqual(queryKeys.quotations.detail(4));
    expect(keys()).toContainEqual(queryKeys.quotations.lists());
    expect(keys()).toContainEqual(queryKeys.quotations.statusCountsAll());
    expect(keys()).toContainEqual(queryKeys.enquiries.detail(8));
    expect(keys()).toContainEqual(queryKeys.contacts.detail(7));
  });
});
