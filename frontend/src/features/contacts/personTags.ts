/**
 * GAP-040 F1: the canonical, ordered customer-tag taxonomy.
 *
 * The backend accepts/returns these exact `value`s (PATCH replaces the whole
 * set; unknown values are rejected with a 400). The UI iterates this array for
 * a stable display order; `labelKey` resolves to a `contacts` i18n key.
 *
 * "Repeat" is deliberately excluded — it is derived from booking history, not a
 * manual tag.
 */
export interface PersonTag {
  value: string;
  labelKey: string;
}

export const PERSON_TAGS: readonly PersonTag[] = [
  { value: "vip", labelKey: "tags.vip" },
  { value: "trade", labelKey: "tags.trade" },
  { value: "pa", labelKey: "tags.pa" },
  { value: "nicks_friend", labelKey: "tags.nicks_friend" },
  { value: "nicks_network", labelKey: "tags.nicks_network" },
  { value: "disability", labelKey: "tags.disability" },
  { value: "approach_with_care", labelKey: "tags.approach_with_care" },
  { value: "past_issues", labelKey: "tags.past_issues" },
  { value: "specific_preferences", labelKey: "tags.specific_preferences" },
  { value: "time_waster", labelKey: "tags.time_waster" },
] as const;
