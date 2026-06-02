import { useTranslation } from "react-i18next";
import { statusToneVar, type StatusTone } from "@/styles/tokens";

/**
 * Days-to-arrival pill with a tone ramp: imminent stays glow danger, near-term
 * warning, everything else neutral. The matrix only lists live bookings
 * (`date_to >= today`), so a negative countdown means the guest is in
 * residence — not departed. Colours come from the status-tone tokens via
 * inline `color-mix` (the same data-driven pattern as TierBadge) so the pill
 * stays token-only.
 */
function toneFor(days: number): StatusTone {
  if (days <= 3) return "danger";
  if (days <= 14) return "warning";
  return "neutral";
}

export function CountdownPill({ days }: { days: number }) {
  const { t } = useTranslation("concierge");
  const tone = days < 0 ? "neutral" : toneFor(days);
  const color = statusToneVar[tone];
  const label =
    days < 0
      ? t("countdown.in_house")
      : days === 0
        ? t("countdown.today")
        : t("countdown.in_days", { count: days });
  return (
    <span
      className="rounded-pill inline-block border px-2 py-0.5 text-xs font-medium tabular-nums"
      style={{
        borderColor: `color-mix(in oklch, ${color} 40%, transparent)`,
        backgroundColor: `color-mix(in oklch, ${color} 12%, transparent)`,
        color,
      }}
    >
      {label}
    </span>
  );
}
