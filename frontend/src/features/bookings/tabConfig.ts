export const BOOKING_TABS = [
  { slug: "overview", labelKey: "tabs.overview" },
  { slug: "timeline", labelKey: "tabs.timeline" },
  { slug: "notes", labelKey: "tabs.notes" },
  { slug: "finance", labelKey: "tabs.finance" },
  { slug: "payments", labelKey: "tabs.payments" },
  { slug: "concierge", labelKey: "tabs.concierge" },
  { slug: "comms", labelKey: "tabs.comms" },
  { slug: "owner", labelKey: "tabs.owner" },
] as const;

export type BookingTabSlug = (typeof BOOKING_TABS)[number]["slug"];
