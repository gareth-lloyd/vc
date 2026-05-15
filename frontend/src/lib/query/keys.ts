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
    nearby: (idOrSlug: PropertyId) => ["properties", "detail", idOrSlug, "nearby"] as const,
    changeover: (idOrSlug: PropertyId) => ["properties", "detail", idOrSlug, "changeover"] as const,
    seasons: (idOrSlug: PropertyId) => ["properties", "detail", idOrSlug, "seasons"] as const,
    seasonDetail: (seasonId: SeasonId) => ["properties", "seasons", "detail", seasonId] as const,
    extras: (idOrSlug: PropertyId) => ["properties", "detail", idOrSlug, "extras"] as const,
    discounts: (idOrSlug: PropertyId) => ["properties", "detail", idOrSlug, "discounts"] as const,
    contacts: (idOrSlug: PropertyId) => ["properties", "detail", idOrSlug, "contacts"] as const,
    images: (idOrSlug: PropertyId) => ["properties", "detail", idOrSlug, "images"] as const,
    settings: (idOrSlug: PropertyId) => ["properties", "detail", idOrSlug, "settings"] as const,
    finance: (idOrSlug: PropertyId) => ["properties", "detail", idOrSlug, "finance"] as const,
    holdsRoot: (propertyId: number) => ["properties", "detail", propertyId, "holds"] as const,
    holds: (propertyId: number, from: string, to: string) =>
      ["properties", "detail", propertyId, "holds", from, to] as const,
    availabilityRoot: (propertyId: number) =>
      ["properties", "detail", propertyId, "availability"] as const,
    availabilityCalendar: (propertyId: number, from: string, to: string) =>
      ["properties", "detail", propertyId, "availability", from, to] as const,
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
  countries: {
    all: () => ["countries"] as const,
    lists: () => ["countries", "list"] as const,
    list: <F>(filters: F) => ["countries", "list", filters] as const,
    detail: (iso2: string) => ["countries", "detail", iso2] as const,
  },
  currencies: {
    all: () => ["currencies"] as const,
    lists: () => ["currencies", "list"] as const,
    list: <F>(filters: F) => ["currencies", "list", filters] as const,
    detail: (code: string) => ["currencies", "detail", code] as const,
  },
  tagFeatures: {
    all: () => ["features"] as const,
    lists: () => ["features", "list"] as const,
    list: <F>(filters: F) => ["features", "list", filters] as const,
    detail: (id: number | string) => ["features", "detail", id] as const,
  },
  tagFeatureCategories: {
    all: () => ["feature-categories"] as const,
    lists: () => ["feature-categories", "list"] as const,
    list: <F>(filters: F) => ["feature-categories", "list", filters] as const,
    detail: (id: number | string) => ["feature-categories", "detail", id] as const,
  },
  systemSettings: {
    all: () => ["system", "settings"] as const,
  },
  nearbyPlaceTypes: {
    all: () => ["nearby-place-types"] as const,
    list: () => ["nearby-place-types", "list"] as const,
  },
} as const;
