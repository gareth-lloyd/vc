import i18n from "@/i18n";
import type { Guest } from "./schemas";

export function guestDisplayName(guest: Pick<Guest, "first_name" | "last_name" | "id">): string {
  const full = [guest.first_name, guest.last_name].filter(Boolean).join(" ").trim();
  if (full) return full;
  return i18n.t("guests:fallback.name_with_id", { id: guest.id });
}
