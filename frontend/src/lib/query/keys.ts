export type PropertyId = string | number;
export type BookingId = string | number;

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
  },
  bookings: {
    all: () => ["bookings"] as const,
    list: <F>(filters: F) => ["bookings", "list", filters] as const,
    detail: (id: BookingId) => ["bookings", "detail", id] as const,
    activity: (id: BookingId) => ["bookings", "detail", id, "activity"] as const,
    notes: (id: BookingId) => ["bookings", "detail", id, "notes"] as const,
    conciergeItems: (id: BookingId) => ["bookings", "detail", id, "concierge-items"] as const,
  },
} as const;
