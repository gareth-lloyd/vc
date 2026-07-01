export type PropertyId = string | number;
export type BookingId = string | number;
export type RatePlanId = string | number;
export type ContactId = string | number;
export type CompanyId = string | number;
export type EnquiryId = string | number;
export type UserId = string | number;
export type QuotationId = string | number;

// Entity ids reach the key factory two ways: as a number (from a Zod-parsed
// `entity.id`, used by mutation success handlers) and as a string (from
// `useParams`, used by detail layouts). React Query hashes keys with
// JSON.stringify, so `51 !== "51"` would split the same logical entity across
// two cache entries — the mutation writes one, the layout observes the other,
// and the display never refreshes. Normalize every id-position element to a
// string so both paths hash identically. Slugs and codes are already strings,
// so this is a no-op for them.
const k = (id: string | number): string => String(id);

export const queryKeys = {
  auth: {
    me: () => ["auth", "me"] as const,
  },
  owner: {
    all: () => ["owner"] as const,
    me: () => ["owner", "me"] as const,
    dashboard: () => ["owner", "dashboard"] as const,
    properties: <F>(filters: F) => ["owner", "properties", filters] as const,
    property: (id: PropertyId) => ["owner", "properties", "detail", k(id)] as const,
    propertyCalendar: (id: PropertyId, from: string, to: string) =>
      ["owner", "properties", "detail", k(id), "calendar", from, to] as const,
    bookings: <F>(filters: F) => ["owner", "bookings", filters] as const,
    booking: (id: BookingId) => ["owner", "bookings", "detail", k(id)] as const,
    blockRequests: <F>(filters: F) => ["owner", "block-requests", filters] as const,
  },
  properties: {
    all: () => ["properties"] as const,
    list: <F>(filters: F) => ["properties", "list", filters] as const,
    detail: (idOrSlug: PropertyId) => ["properties", "detail", k(idOrSlug)] as const,
    descriptions: (idOrSlug: PropertyId) =>
      ["properties", "detail", k(idOrSlug), "descriptions"] as const,
    features: (idOrSlug: PropertyId) => ["properties", "detail", k(idOrSlug), "features"] as const,
    rooms: (idOrSlug: PropertyId) => ["properties", "detail", k(idOrSlug), "rooms"] as const,
    nearby: (idOrSlug: PropertyId) => ["properties", "detail", k(idOrSlug), "nearby"] as const,
    services: (idOrSlug: PropertyId) => ["properties", "detail", k(idOrSlug), "services"] as const,
    changeover: (idOrSlug: PropertyId) =>
      ["properties", "detail", k(idOrSlug), "changeover"] as const,
    ratePlans: (idOrSlug: PropertyId) => ["properties", "detail", k(idOrSlug), "seasons"] as const,
    ratePlanDetail: (ratePlanId: RatePlanId) =>
      ["properties", "seasons", "detail", k(ratePlanId)] as const,
    extras: (idOrSlug: PropertyId) => ["properties", "detail", k(idOrSlug), "extras"] as const,
    discounts: (idOrSlug: PropertyId) =>
      ["properties", "detail", k(idOrSlug), "discounts"] as const,
    contacts: (idOrSlug: PropertyId) => ["properties", "detail", k(idOrSlug), "contacts"] as const,
    images: (idOrSlug: PropertyId) => ["properties", "detail", k(idOrSlug), "images"] as const,
    capacity: (idOrSlug: PropertyId) => ["properties", "detail", k(idOrSlug), "capacity"] as const,
    settings: (idOrSlug: PropertyId) => ["properties", "detail", k(idOrSlug), "settings"] as const,
    finance: (idOrSlug: PropertyId) => ["properties", "detail", k(idOrSlug), "finance"] as const,
    location: (idOrSlug: PropertyId) => ["properties", "detail", k(idOrSlug), "location"] as const,
    holdsRoot: (propertyId: number) => ["properties", "detail", k(propertyId), "holds"] as const,
    holds: (propertyId: number, from: string, to: string) =>
      ["properties", "detail", k(propertyId), "holds", from, to] as const,
    availabilityRoot: (propertyId: number) =>
      ["properties", "detail", k(propertyId), "availability"] as const,
    availabilityCalendar: (propertyId: number, from: string, to: string) =>
      ["properties", "detail", k(propertyId), "availability", from, to] as const,
    bookingsInRange: (propertyId: number, from: string, to: string) =>
      ["properties", "detail", k(propertyId), "bookings", from, to] as const,
  },
  contacts: {
    all: () => ["contacts"] as const,
    lists: () => ["contacts", "list"] as const,
    list: <F>(filters: F) => ["contacts", "list", filters] as const,
    detail: (id: ContactId) => ["contacts", "detail", k(id)] as const,
    properties: (id: ContactId) => ["contacts", "detail", k(id), "properties"] as const,
    enquiries: (id: ContactId) => ["contacts", "detail", k(id), "enquiries"] as const,
    bookings: (id: ContactId) => ["contacts", "detail", k(id), "bookings"] as const,
    relationships: (id: ContactId) => ["contacts", "detail", k(id), "relationships"] as const,
    // `kind` and `status` are part of the cache key: the same query string
    // scoped to `contact` (business directory) vs `customer` (enquiry picker),
    // or filtered by a different `status`, must not collide, or one picker would
    // serve the other's results.
    search: (q: string, kind: string = "contact", status?: string) =>
      ["contacts", "search", kind, status ?? "all", q] as const,
  },
  companies: {
    all: () => ["companies"] as const,
    lists: () => ["companies", "list"] as const,
    list: <F>(filters: F) => ["companies", "list", filters] as const,
    detail: (id: CompanyId) => ["companies", "detail", k(id)] as const,
    // `status` is part of the cache key so a search scoped to active orgs can't
    // collide with an unscoped one and serve the wrong picker results.
    search: (q: string, status?: string) => ["companies", "search", status ?? "all", q] as const,
  },
  clients: {
    // List-only read-only directory: `all()` is the conventional invalidation
    // root; only `list()` has a consumer today (no detail/CRUD/picker).
    all: () => ["clients"] as const,
    list: <F>(filters: F) => ["clients", "list", filters] as const,
  },
  bookings: {
    all: () => ["bookings"] as const,
    lists: () => ["bookings", "list"] as const,
    list: <F>(filters: F) => ["bookings", "list", filters] as const,
    statusCountsAll: () => ["bookings", "status-counts"] as const,
    statusCounts: <F>(filters: F) => ["bookings", "status-counts", filters] as const,
    detail: (id: BookingId) => ["bookings", "detail", k(id)] as const,
    activity: (id: BookingId) => ["bookings", "detail", k(id), "activity"] as const,
    notes: (id: BookingId) => ["bookings", "detail", k(id), "notes"] as const,
    conciergeItems: (id: BookingId) => ["bookings", "detail", k(id), "concierge-items"] as const,
    chargeItems: (id: BookingId) => ["bookings", "detail", k(id), "charge-items"] as const,
    damageClaims: (id: BookingId) => ["bookings", "detail", k(id), "damage-claims"] as const,
    deposit: (id: BookingId) => ["bookings", "detail", k(id), "deposit"] as const,
    balance: (id: BookingId) => ["bookings", "detail", k(id), "balance"] as const,
    security: (id: BookingId) => ["bookings", "detail", k(id), "security"] as const,
    securityDeposit: (id: BookingId) => ["bookings", "detail", k(id), "security-deposit"] as const,
    refunds: (id: BookingId) => ["bookings", "detail", k(id), "refunds"] as const,
    emails: (id: BookingId) => ["bookings", "detail", k(id), "emails"] as const,
  },
  enquiries: {
    all: () => ["enquiries"] as const,
    lists: () => ["enquiries", "list"] as const,
    list: <F>(filters: F) => ["enquiries", "list", filters] as const,
    statusCountsAll: () => ["enquiries", "status-counts"] as const,
    statusCounts: <F>(filters: F) => ["enquiries", "status-counts", filters] as const,
    detail: (id: EnquiryId) => ["enquiries", "detail", k(id)] as const,
    activity: (id: EnquiryId) => ["enquiries", "detail", k(id), "activity"] as const,
    notes: (id: EnquiryId) => ["enquiries", "detail", k(id), "notes"] as const,
  },
  dashboard: {
    all: () => ["dashboard"] as const,
    arrivalsToday: (date: string) => ["dashboard", "arrivals-today", date] as const,
    departuresTodayCount: (date: string) => ["dashboard", "departures-today-count", date] as const,
    newEnquiriesCount: () => ["dashboard", "new-enquiries-count"] as const,
    awaitingBalanceCount: () => ["dashboard", "awaiting-balance-count"] as const,
    recentEnquiries: () => ["dashboard", "recent-enquiries"] as const,
  },
  users: {
    all: () => ["users"] as const,
    lists: () => ["users", "list"] as const,
    list: <F>(filters: F) => ["users", "list", filters] as const,
    detail: (id: UserId) => ["users", "detail", k(id)] as const,
  },
  quotations: {
    all: () => ["quotations"] as const,
    lists: () => ["quotations", "list"] as const,
    list: <F>(filters: F) => ["quotations", "list", filters] as const,
    statusCountsAll: () => ["quotations", "status-counts"] as const,
    statusCounts: <F>(filters: F) => ["quotations", "status-counts", filters] as const,
    detail: (id: QuotationId) => ["quotations", "detail", k(id)] as const,
    lines: (id: QuotationId) => ["quotations", "detail", k(id), "lines"] as const,
    preview: (id: QuotationId, overrides?: unknown) =>
      ["quotations", "detail", k(id), "preview", overrides ?? null] as const,
  },
  concierge: {
    all: () => ["concierge"] as const,
    overview: () => ["concierge", "overview"] as const,
  },
  audit: {
    all: () => ["audit"] as const,
    list: <F>(filters: F) => ["audit", "list", filters] as const,
  },
  ownerBlockUpdates: {
    all: () => ["owner-block-updates"] as const,
    list: <F>(filters: F) => ["owner-block-updates", "list", filters] as const,
  },
  availability: {
    all: () => ["availability"] as const,
    timeline: (ids: number[], from: string, to: string) =>
      ["availability", "timeline", ids.map(k), from, to] as const,
    weeklyPrices: (ids: number[], from: string, to: string) =>
      ["availability", "weekly-prices", ids.map(k), from, to] as const,
  },
  regions: {
    all: () => ["regions"] as const,
    list: () => ["regions", "list"] as const,
  },
  propertyCategories: {
    all: () => ["property-categories"] as const,
    list: () => ["property-categories", "list"] as const,
  },
  propertyGroups: {
    all: () => ["property-groups"] as const,
    list: () => ["property-groups", "list"] as const,
  },
  collections: {
    all: () => ["collections"] as const,
    list: () => ["collections", "list"] as const,
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
    detail: (id: number | string) => ["features", "detail", k(id)] as const,
  },
  tagFeatureCategories: {
    all: () => ["feature-categories"] as const,
    lists: () => ["feature-categories", "list"] as const,
    list: <F>(filters: F) => ["feature-categories", "list", filters] as const,
    detail: (id: number | string) => ["feature-categories", "detail", k(id)] as const,
  },
  emailTemplates: {
    all: () => ["email-templates"] as const,
    lists: () => ["email-templates", "list"] as const,
    list: <F>(filters: F) => ["email-templates", "list", filters] as const,
    detail: (key: string) => ["email-templates", "detail", key] as const,
    preview: (key: string, overrides?: unknown) =>
      ["email-templates", "detail", key, "preview", overrides ?? null] as const,
    versions: (key: string) => ["email-templates", "detail", key, "versions"] as const,
  },
  systemSettings: {
    all: () => ["system", "settings"] as const,
  },
  nearbyPlaceTypes: {
    all: () => ["nearby-place-types"] as const,
    list: () => ["nearby-place-types", "list"] as const,
  },
} as const;
