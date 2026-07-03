import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";

/**
 * GAP-052: the contact's derived type(s) — every capacity the person holds
 * (customer / agent / property roles like owner, manager) shown as badges so a
 * dual-hat contact surfaces all of them at a glance. Values come from the
 * backend `contact_types` field; an unknown value falls back to its raw string
 * rather than vanishing. Empty → nothing. Distinct from `tags` (the client-only
 * flag set rendered by TagChips).
 *
 * `prominent` renders a larger, accent-filled chip for the detail-page header,
 * where the contact's capacity is a headline fact; the default small secondary
 * chip suits dense contexts (list cells, profile panel).
 */
export function ContactTypeBadges({
  types,
  prominent = false,
}: {
  types: string[];
  prominent?: boolean;
}) {
  const { t } = useTranslation("contacts");
  if (types.length === 0) return null;
  return (
    <div className={prominent ? "flex flex-wrap gap-1.5" : "flex flex-wrap gap-1"}>
      {types.map((type) =>
        prominent ? (
          <Badge
            key={type}
            className="px-3 py-1 text-sm font-semibold tracking-wide uppercase"
            style={{ backgroundColor: "var(--accent-700)", color: "var(--accent-50)" }}
          >
            {t(`types.${type}`, { defaultValue: type })}
          </Badge>
        ) : (
          <Badge key={type} variant="secondary">
            {t(`types.${type}`, { defaultValue: type })}
          </Badge>
        ),
      )}
    </div>
  );
}
