import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";

/**
 * GAP-052: the contact's derived type(s) — every capacity the person holds
 * (customer / agent / property roles like owner, manager) shown as badges so a
 * dual-hat contact surfaces all of them at a glance. Values come from the
 * backend `contact_types` field; an unknown value falls back to its raw string
 * rather than vanishing. Empty → nothing. Distinct from `tags` (the client-only
 * flag set rendered by TagChips).
 */
export function ContactTypeBadges({ types }: { types: string[] }) {
  const { t } = useTranslation("contacts");
  if (types.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {types.map((type) => (
        <Badge key={type} variant="secondary">
          {t(`types.${type}`, { defaultValue: type })}
        </Badge>
      ))}
    </div>
  );
}
