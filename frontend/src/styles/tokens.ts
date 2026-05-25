/**
 * Typed references to the CSS custom-property tokens defined in `globals.css`.
 *
 * Use these instead of stringly-typed `var(--…)` calls. The colour values
 * themselves live in CSS — re-skinning the app is still a single-file edit
 * to `globals.css`.
 */

export const STATUS_TONES = ["success", "warning", "danger", "info", "neutral", "hold"] as const;

export type StatusTone = (typeof STATUS_TONES)[number];

export const statusToneVar: Record<StatusTone, string> = {
  success: "var(--status-success)",
  warning: "var(--status-warning)",
  danger: "var(--status-danger)",
  info: "var(--status-info)",
  neutral: "var(--status-neutral)",
  hold: "var(--status-hold)",
};

export const SERVICE_KEYS = [
  "car",
  "transfers",
  "boat",
  "chef",
  "grocery",
  "firstnight",
  "restaurant",
  "gifting",
  "activities",
  "spa",
  "wine",
  "nanny",
  "other",
] as const;

export type ServiceKey = (typeof SERVICE_KEYS)[number];

export const serviceColorVar: Record<ServiceKey, string> = {
  car: "var(--svc-car)",
  transfers: "var(--svc-transfers)",
  boat: "var(--svc-boat)",
  chef: "var(--svc-chef)",
  grocery: "var(--svc-grocery)",
  firstnight: "var(--svc-firstnight)",
  restaurant: "var(--svc-restaurant)",
  gifting: "var(--svc-gifting)",
  activities: "var(--svc-activities)",
  spa: "var(--svc-spa)",
  wine: "var(--svc-wine)",
  nanny: "var(--svc-nanny)",
  other: "var(--svc-other)",
};

export const LEAD_STATUSES = ["hot", "warm", "cold", "dead"] as const;
export type LeadStatus = (typeof LEAD_STATUSES)[number];

export const leadStatusColorVar: Record<LeadStatus, string> = {
  hot: "var(--lead-hot)",
  warm: "var(--lead-warm)",
  cold: "var(--lead-cold)",
  dead: "var(--lead-dead)",
};

export const TIERS = ["quintessential", "signature"] as const;
export type Tier = (typeof TIERS)[number];

export const tierColorVar: Record<Tier, string> = {
  quintessential: "var(--tier-quintessential)",
  signature: "var(--tier-signature)",
};
