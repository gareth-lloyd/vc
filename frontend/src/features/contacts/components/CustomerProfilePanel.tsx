import { useTranslation } from "react-i18next";
import type { ContactId } from "@/lib/query/keys";
import { useContact } from "../hooks";
import { contactDisplayName } from "../display";
import { RepeatBadge } from "./RepeatBadge";
import { TagChips } from "./TagChips";
import { ContactAddressSection } from "./ContactAddressSection";
import { LinkedContactsAccordion } from "./LinkedContactsAccordion";
import { ContactEnquiryHistory } from "./ContactEnquiryHistory";
import { ContactBookingHistory } from "./ContactBookingHistory";

interface CustomerProfilePanelProps {
  /** The Person whose 360 profile to show; null when no customer is linked yet. */
  personId: ContactId | null | undefined;
}

/**
 * GAP-042: the customer-360 profile as a self-contained panel — identity, tags,
 * hideable address, linked contacts, and enquiry/booking history over one
 * Person. Reused by the contact detail page and embedded in the enquiry and
 * quotation rails so all three render from a single source.
 */
export function CustomerProfilePanel({ personId }: CustomerProfilePanelProps) {
  const { t } = useTranslation("contacts");
  // Hook runs unconditionally; disabled (no fetch) when personId is absent.
  const query = useContact(personId ?? undefined);

  if (personId == null) {
    return <p className="text-muted-foreground text-sm">{t("profile.empty")}</p>;
  }
  if (query.isLoading) {
    return <p className="text-muted-foreground text-sm">{t("history.loading")}</p>;
  }
  if (query.isError || !query.data) {
    return <p className="text-destructive text-sm">{t("errors.detail_load_failed_title")}</p>;
  }

  const contact = query.data;
  return (
    <div className="space-y-3">
      <div>
        <p className="text-foreground text-sm font-semibold">{contactDisplayName(contact)}</p>
        {contact.agency_detail?.name ? (
          <p className="text-muted-foreground text-xs">{contact.agency_detail.name}</p>
        ) : null}
      </div>
      <RepeatBadge
        bookingCount={contact.booking_count ?? 0}
        isRepeat={contact.is_repeat_customer ?? false}
      />
      {(contact.tags ?? []).length > 0 ? <TagChips tags={contact.tags ?? []} /> : null}
      <ContactAddressSection contact={contact} />
      <LinkedContactsAccordion contactId={contact.id} />
      <ContactEnquiryHistory contactId={contact.id} />
      <ContactBookingHistory contactId={contact.id} />
    </div>
  );
}
