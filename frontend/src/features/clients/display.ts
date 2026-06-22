import i18n from "@/i18n";
import type { ClientListItem } from "./schemas";

export function clientDisplayName(
  client: Pick<ClientListItem, "id" | "first_name" | "last_name">,
): string {
  const name = [client.first_name, client.last_name].filter(Boolean).join(" ").trim();
  return name || i18n.t("clients:fallback.name_with_id", { id: client.id });
}
