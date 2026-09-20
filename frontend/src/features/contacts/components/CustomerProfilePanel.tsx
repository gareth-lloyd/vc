import { useTranslation } from "react-i18next";
import type { ContactId } from "@/lib/query/keys";
import { useContact } from "../hooks";
import { contactDisplayName, isClientContact } from "../display";
import { RepeatBadge } from "./RepeatBadge";
import { TagChips } from "./TagChips";
import { InlineTagEditor } from "./InlineTagEditor";
import { ContactTypeBadges } from "./ContactTypeBadges";
import { ContactAddressSection } from "./ContactAddressSection";
import { LinkedContactsAccordion } from "./LinkedContactsAccordion";
import { ContactEnquiryHistory } from "./ContactEnquiryHistory";
import { ContactBookingHistory } from "./ContactBookingHistory";
import { ContactPastStayHistory } from "./ContactPastStayHistory";

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
  // GAP-118: the migration's unknown-client sentinel is a placeholder, not a
  // customer. Same hint as an absent link, and deliberately before the
  // identity/tags block: rendering it as a contact invites an operator to tag
  // or edit a row that stands for "we could not resolve this".
  if (contact.is_unknown_client === true) {
    return <p className="text-muted-foreground text-sm">{t("profile.empty")}</p>;
  }
  return (
    <div className="space-y-3">
      <div>
        <p className="text-foreground text-sm font-semibold">{contactDisplayName(contact)}</p>
        {contact.agency_detail?.name ? (
          <p className="text-muted-foreground text-xs">{contact.agency_detail.name}</p>
        ) : null}
      </div>
      <ContactTypeBadges types={contact.contact_types ?? []} />
      <RepeatBadge
        bookingCount={contact.booking_count ?? 0}
        pastStayCount={contact.past_stay_count ?? 0}
        isRepeat={contact.is_repeat_customer ?? false}
      />
      {isClientContact(contact) ? (
        <InlineTagEditor contactId={contact.id} tags={contact.tags ?? []} />
      ) : (contact.tags ?? []).length > 0 ? (
        <TagChips tags={contact.tags ?? []} />
      ) : null}
      <ContactAddressSection contact={contact} />
      <LinkedContactsAccordion contactId={contact.id} />
      <ContactEnquiryHistory contactId={contact.id} />
      <ContactBookingHistory contactId={contact.id} />
      <ContactPastStayHistory contactId={contact.id} />
    </div>
  );
}
