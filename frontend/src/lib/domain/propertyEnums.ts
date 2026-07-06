// Shared property-configuration enum tuples (mirror the backend `properties`
// enums). They live in `lib/domain` so any feature — `properties` itself plus
// the `admin/property-defaults` editor — can consume them without a
// cross-feature import (GAP-063/GAP-072 module boundaries). `properties/schemas`
// re-exports these for its own intra-feature callers.

export const PROPERTY_AVAILABILITY_DEFAULTS = ["available", "unavailable", "on_request"] as const;

export const PROPERTY_CHANGEOVER_DAYS = [
  "mon",
  "tue",
  "wed",
  "thu",
  "fri",
  "sat",
  "sun",
  "any",
] as const;

export const PROPERTY_PRICE_BASES = ["gross", "net"] as const;
