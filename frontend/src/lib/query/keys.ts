export type PropertyId = string | number;
export type BookingId = string | number;
export type SeasonId = string | number;
export type ContactId = string | number;
export type EnquiryId = string | number;
export type UserId = string | number;
export type QuotationId = string | number;

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
    images: (idOrSlug: PropertyId) => ["properties", "detail", idOrSlug, "images"] as const,
    settings: (idOrSlug: PropertyId) => ["properties", "detail", idOrSlug, "settings"] as const,
    finance: (idOrSlug: PropertyId) => ["properties", "detail", idOrSlug, "finance"] as const,
    holds: (propertyId: number, from: string, to: string) =>
      ["properties", "detail", propertyId, "holds", from, to] as const,
    bookingsInRange: (propertyId: number, from: string, to: string) =>
      ["properties", "detail", propertyId, "bookings", from, to] as const,
  },
  contacts: {
    all: () => ["contacts"] as const,
    lists: () => ["contacts", "list"] as const,
    list: <F>(filters: F) => ["contacts", "list", filters] as const,
    detail: (id: ContactId) => ["contacts", "detail", id] as const,
    properties: (id: ContactId) => ["contacts", "detail", id, "properties"] as const,
    search: (q: string) => ["contacts", "search", q] as const,
  },
  bookings: {
    all: () => ["bookings"] as const,
    lists: () => ["bookings", "list"] as const,
    list: <F>(filters: F) => ["bookings", "list", filters] as const,
    detail: (id: BookingId) => ["bookings", "detail", id] as const,
    activity: (id: BookingId) => ["bookings", "detail", id, "activity"] as const,
    notes: (id: BookingId) => ["bookings", "detail", id, "notes"] as const,
    conciergeItems: (id: BookingId) => ["bookings", "detail", id, "concierge-items"] as const,
    deposit: (id: BookingId) => ["bookings", "detail", id, "deposit"] as const,
    balance: (id: BookingId) => ["bookings", "detail", id, "balance"] as const,
    security: (id: BookingId) => ["bookings", "detail", id, "security"] as const,
  },
  enquiries: {
    all: () => ["enquiries"] as const,
    lists: () => ["enquiries", "list"] as const,
    list: <F>(filters: F) => ["enquiries", "list", filters] as const,
    detail: (id: EnquiryId) => ["enquiries", "detail", id] as const,
    activity: (id: EnquiryId) => ["enquiries", "detail", id, "activity"] as const,
    notes: (id: EnquiryId) => ["enquiries", "detail", id, "notes"] as const,
  },
  users: {
    all: () => ["users"] as const,
    lists: () => ["users", "list"] as const,
    list: <F>(filters: F) => ["users", "list", filters] as const,
    detail: (id: UserId) => ["users", "detail", id] as const,
  },
  quotations: {
    all: () => ["quotations"] as const,
    lists: () => ["quotations", "list"] as const,
    list: <F>(filters: F) => ["quotations", "list", filters] as const,
    detail: (id: QuotationId) => ["quotations", "detail", id] as const,
    lines: (id: QuotationId) => ["quotations", "detail", id, "lines"] as const,
  },
  audit: {
    all: () => ["audit"] as const,
    list: <F>(filters: F) => ["audit", "list", filters] as const,
  },
} as const;
