export const PROPERTY_TABS = [
  { slug: "details", labelKey: "tabs.details" },
  { slug: "rooms", labelKey: "tabs.rooms" },
  { slug: "nearby", labelKey: "tabs.nearby" },
  { slug: "pricing", labelKey: "tabs.pricing" },
  { slug: "availability", labelKey: "tabs.availability" },
  { slug: "people", labelKey: "tabs.people" },
  { slug: "media", labelKey: "tabs.media" },
  { slug: "features", labelKey: "tabs.features" },
  { slug: "settings", labelKey: "tabs.settings" },
] as const;

export type PropertyTabSlug = (typeof PROPERTY_TABS)[number]["slug"];

export const PROPERTY_TAB_SLUGS: readonly PropertyTabSlug[] = PROPERTY_TABS.map((t) => t.slug);
