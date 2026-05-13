export type PropertyId = string | number;
export type BookingId = string | number;
export type SeasonId = string | number;
export type ContactId = string | number;

export const queryKeys = {
  auth: {
    me: () => ["auth", "me"] as const,
  },
  properties: {
    all: () => ["properties"] as const,
    list: <F>(filters: F) => ["properties", "list", filters] as const,
    detail: (idOrSlug: PropertyId) => ["properties", "detail", idOrSlug] as const,
    descriptions: (idOrSlug: PropertyId) =>
      ["properties", "detail", idOrSlug, "descriptions"] as const,
    features: (idOrSlug: PropertyId) => ["properties", "detail", idOrSlug, "features"] as const,
    rooms: (idOrSlug: PropertyId) => ["properties", "detail", idOrSlug, "rooms"] as const,
    seasons: (idOrSlug: PropertyId) => ["properties", "detail", idOrSlug, "seasons"] as const,
    seasonDetail: (seasonId: SeasonId) => ["properties", "seasons", "detail", seasonId] as const,
    extras: (idOrSlug: PropertyId) => ["properties", "detail", idOrSlug, "extras"] as const,
    discounts: (idOrSlug: PropertyId) => ["properties", "detail", idOrSlug, "discounts"] as const,
    contacts: (idOrSlug: PropertyId) => ["properties", "detail", idOrSlug, "contacts"] as const,
    holds: (propertyId: number, from: string, to: string) =>
      ["properties", "detail", propertyId, "holds", from, to] as const,
    bookingsInRange: (propertyId: number, from: string, to: string) =>
      ["properties", "detail", propertyId, "bookings", from, to] as const,
  },
  contacts: {
    detail: (id: ContactId) => ["contacts", "detail", id] as const,
  },
  bookings: {
    all: () => ["bookings"] as const,
    lists: () => ["bookings", "list"] as const,
    list: <F>(filters: F) => ["bookings", "list", filters] as const,
    detail: (id: BookingId) => ["bookings", "detail", id] as const,
    activity: (id: BookingId) => ["bookings", "detail", id, "activity"] as const,
    notes: (id: BookingId) => ["bookings", "detail", id, "notes"] as const,
    conciergeItems: (id: BookingId) => ["bookings", "detail", id, "concierge-items"] as const,
  },
} as const;
