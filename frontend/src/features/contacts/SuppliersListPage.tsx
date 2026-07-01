import { ContactsListPage } from "./ContactsListPage";

/**
 * GAP-048: the operator-side "Suppliers" directory. A thin wrapper that pins the
 * `directory=suppliers` scoping on the shared contacts list (kind=CONTACT minus
 * agent-capacity); rows still link to the shared `/contacts/:id` detail.
 */
export function SuppliersListPage() {
  return <ContactsListPage directory="suppliers" />;
}
