import { useOutletContext } from "react-router-dom";
import { AuditHistory } from "@/features/audit/AuditHistory";
import type { ContactOutletContext } from "../ContactDetailLayout";

export function AuditTab() {
  const { contact } = useOutletContext<ContactOutletContext>();
  // Contacts are `accounts.Person` rows since GAP-045 unified human identity.
  return (
    <div className="p-6">
      <AuditHistory entityType="accounts.person" entityId={contact.id} />
    </div>
  );
}
