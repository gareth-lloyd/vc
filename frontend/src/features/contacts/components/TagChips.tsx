import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { PERSON_TAGS } from "../personTags";

/**
 * Renders a contact's customer tags as chips, labelled via the PERSON_TAGS
 * taxonomy (GAP-040 F1). An unknown value falls back to its raw string rather
 * than vanishing. Chips sort by label for a stable order. Empty → nothing.
 */
export function TagChips({ tags }: { tags: string[] }) {
  const { t } = useTranslation("contacts");
  const labelByValue = useMemo(() => {
    const map = new Map<string, string>();
    PERSON_TAGS.forEach((tag) => map.set(tag.value, t(tag.labelKey)));
    return map;
  }, [t]);

  if (tags.length === 0) return null;

  const chips = tags
    .map((value) => ({ value, label: labelByValue.get(value) ?? value }))
    .sort((a, b) => a.label.localeCompare(b.label));

  return (
    <div className="flex flex-wrap gap-1">
      {chips.map((chip) => (
        <Badge key={chip.value} variant="outline">
          {chip.label}
        </Badge>
      ))}
    </div>
  );
}
