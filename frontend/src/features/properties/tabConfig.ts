// Nav order. Features follows Descriptions so a villa's website copy and its
// amenities are reviewed side by side; the `media` slug keeps its route but is
// labelled "Images" (2026-09-22). PropertyDetailLayout.test.tsx pins the order.
export const PROPERTY_TABS = [
  { slug: "details", labelKey: "tabs.details" },
  { slug: "descriptions", labelKey: "tabs.descriptions" },
  { slug: "features", labelKey: "tabs.features" },
  { slug: "rooms", labelKey: "tabs.rooms" },
  { slug: "nearby", labelKey: "tabs.nearby" },
  { slug: "rate-workbench", labelKey: "tabs.rate_workbench" },
  { slug: "services", labelKey: "tabs.services" },
  { slug: "availability", labelKey: "tabs.availability" },
  { slug: "people", labelKey: "tabs.people" },
  { slug: "media", labelKey: "tabs.media" },
  { slug: "settings", labelKey: "tabs.settings" },
  { slug: "history", labelKey: "tabs.history" },
] as const;

export type PropertyTabSlug = (typeof PROPERTY_TABS)[number]["slug"];

export const PROPERTY_TAB_SLUGS: readonly PropertyTabSlug[] = PROPERTY_TABS.map((t) => t.slug);
