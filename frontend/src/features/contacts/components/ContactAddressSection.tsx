import { useTranslation } from "react-i18next";
import { FactList, FactRow } from "@/components/data/FactList";
import { Collapsible } from "@/components/ui/collapsible";
import type { Contact } from "../schemas";

/**
 * GAP-042: the contact's postal address as a collapsible aside. The owner noted
 * the address "could be hidden … useful to have it there", so it is collapsed by
 * default and shared between the full DetailsTab and the compact profile panel.
 */
export function ContactAddressSection({ contact }: { contact: Contact }) {
  const { t } = useTranslation("contacts");
  return (
    <Collapsible
      className="rounded-md border"
      headerClassName="px-3 py-2 text-sm font-medium"
      title={t("headings.address")}
    >
      <div className="border-border border-t px-3 py-2">
        <FactList>
          <FactRow label={t("fields.address_line_1")} value={contact.address_line_1 || "—"} />
          <FactRow label={t("fields.address_line_2")} value={contact.address_line_2 || "—"} />
          <FactRow label={t("fields.town")} value={contact.town || "—"} />
          <FactRow label={t("fields.post_code")} value={contact.post_code || "—"} />
          <FactRow label={t("fields.country")} value={contact.country_name || "—"} />
        </FactList>
      </div>
    </Collapsible>
  );
}
