import type { TFunction } from "i18next";

/**
 * Render a react-hook-form field error message.
 *
 * Zod schemas carry explicit i18n keys as messages (e.g.
 * `"properties:errors.rule_price_required"`); API errors carry
 * ready-to-display server text. Keys have a namespace prefix and no spaces —
 * translate those, pass anything else through verbatim.
 */
export function fieldErrorText(t: TFunction, message: unknown): string {
  const text = String(message ?? "");
  return /^[a-z0-9_-]+:[a-z0-9_.-]+$/i.test(text) ? t(text as never) : text;
}
