import { useState } from "react";
import { ActivityList } from "@/components/data/ActivityList";
import { useTranslation } from "react-i18next";
import { useOutletContext } from "react-router-dom";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { FactList, FactRow } from "@/components/data/FactList";
import { Section } from "@/components/data/Section";
import { Collapsible } from "@/components/ui/collapsible";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { ApiError } from "@/lib/api/errors";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import {
  useDeleteContactEmail,
  useDeleteContactPhone,
  useSetPrimaryContactEmail,
  useSetPrimaryContactPhone,
} from "../hooks";
import { EmailFormDialog } from "../components/EmailFormDialog";
import { PhoneFormDialog } from "../components/PhoneFormDialog";
import { TagsFormDialog } from "../components/TagsFormDialog";
import { TagChips } from "../components/TagChips";
import { LinkedContactsAccordion } from "../components/LinkedContactsAccordion";
import { ContactEnquiryHistory } from "../components/ContactEnquiryHistory";
import { ContactBookingHistory } from "../components/ContactBookingHistory";
import type { Contact, ContactEmail, ContactPhone } from "../schemas";
import type { ContactOutletContext } from "../ContactDetailLayout";

function EmailsSection({ contact, canWrite }: { contact: Contact; canWrite: boolean }) {
  const { t } = useTranslation("contacts");
  const [addOpen, setAddOpen] = useState(false);
  const [editing, setEditing] = useState<ContactEmail | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const setPrimary = useSetPrimaryContactEmail(contact.id);
  const deleteEmail = useDeleteContactEmail(contact.id);

  const handleDelete = async () => {
    if (deletingId == null) return;
    try {
      await deleteEmail.mutateAsync({ emailId: deletingId });
      toast.success(t("toasts.email_removed"));
      setDeletingId(null);
    } catch (error) {
      const message = error instanceof ApiError ? error.detail : t("toasts.email_remove_failed");
      toast.error(message);
    }
  };

  const handleSetPrimary = async (emailId: number) => {
    try {
      await setPrimary.mutateAsync({ emailId });
    } catch {
      toast.error(t("toasts.set_primary_failed"));
    }
  };

  const addButton = canWrite ? (
    <Button size="sm" variant="outline" onClick={() => setAddOpen(true)}>
      {t("actions.add_email")}
    </Button>
  ) : (
    <Tooltip>
      <TooltipTrigger asChild>
        <span>
          <Button size="sm" variant="outline" disabled>
            {t("actions.add_email")}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>{t("common:tooltips.reservations_role_required")}</TooltipContent>
    </Tooltip>
  );

  return (
    <Section title={t("headings.emails")}>
      <div className="flex items-center justify-end">{addButton}</div>
      {contact.emails.length === 0 ? (
        <EmptyState title={t("empty.emails")} />
      ) : (
        <ActivityList as="ul">
          {contact.emails.map((e) => (
            <li key={e.id} className="flex items-center justify-between gap-4 px-4 py-3 text-sm">
              <div className="flex min-w-0 items-center gap-2">
                <span className="text-foreground truncate">{e.email}</span>
                {e.label ? (
                  <span className="text-muted-foreground/70 text-xs uppercase">{e.label}</span>
                ) : null}
                {e.is_primary ? (
                  <Badge variant="outline">{t("common:status.primary")}</Badge>
                ) : null}
              </div>
              {canWrite ? (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="sm">
                      {t("actions.actions_menu_aria")}
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => setEditing(e)}>
                      {t("common:actions.edit")}
                    </DropdownMenuItem>
                    {!e.is_primary ? (
                      <DropdownMenuItem onClick={() => handleSetPrimary(e.id)}>
                        {t("actions.set_as_primary")}
                      </DropdownMenuItem>
                    ) : null}
                    <DropdownMenuItem
                      className="text-destructive"
                      onClick={() => setDeletingId(e.id)}
                    >
                      {t("common:actions.remove")}
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : null}
            </li>
          ))}
        </ActivityList>
      )}

      {addOpen ? (
        <EmailFormDialog
          mode="create"
          contactId={contact.id}
          open={addOpen}
          onOpenChange={setAddOpen}
        />
      ) : null}
      {editing ? (
        <EmailFormDialog
          mode="edit"
          contactId={contact.id}
          email={editing}
          open={!!editing}
          onOpenChange={(o) => !o && setEditing(null)}
        />
      ) : null}
      {deletingId != null ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setDeletingId(null)}
          onConfirm={handleDelete}
          title={t("confirm.remove_email_title")}
          description={t("confirm.remove_email_body")}
          confirmLabel={t("common:actions.remove")}
          destructive
          busy={deleteEmail.isPending}
        />
      ) : null}
    </Section>
  );
}

function PhonesSection({ contact, canWrite }: { contact: Contact; canWrite: boolean }) {
  const { t } = useTranslation("contacts");
  const [addOpen, setAddOpen] = useState(false);
  const [editing, setEditing] = useState<ContactPhone | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const setPrimary = useSetPrimaryContactPhone(contact.id);
  const deletePhone = useDeleteContactPhone(contact.id);

  const handleDelete = async () => {
    if (deletingId == null) return;
    try {
      await deletePhone.mutateAsync({ phoneId: deletingId });
      toast.success(t("toasts.phone_removed"));
      setDeletingId(null);
    } catch (error) {
      const message = error instanceof ApiError ? error.detail : t("toasts.phone_remove_failed");
      toast.error(message);
    }
  };

  const handleSetPrimary = async (phoneId: number) => {
    try {
      await setPrimary.mutateAsync({ phoneId });
    } catch {
      toast.error(t("toasts.set_primary_failed"));
    }
  };

  const addButton = canWrite ? (
    <Button size="sm" variant="outline" onClick={() => setAddOpen(true)}>
      {t("actions.add_phone")}
    </Button>
  ) : (
    <Tooltip>
      <TooltipTrigger asChild>
        <span>
          <Button size="sm" variant="outline" disabled>
            {t("actions.add_phone")}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>{t("common:tooltips.reservations_role_required")}</TooltipContent>
    </Tooltip>
  );

  return (
    <Section title={t("headings.phones")}>
      <div className="flex items-center justify-end">{addButton}</div>
      {contact.phones.length === 0 ? (
        <EmptyState title={t("empty.phones")} />
      ) : (
        <ActivityList as="ul">
          {contact.phones.map((p) => (
            <li key={p.id} className="flex items-center justify-between gap-4 px-4 py-3 text-sm">
              <div className="flex min-w-0 items-center gap-2">
                <span className="text-foreground truncate">{p.number}</span>
                {p.label ? (
                  <span className="text-muted-foreground/70 text-xs uppercase">{p.label}</span>
                ) : null}
                {p.is_primary ? (
                  <Badge variant="outline">{t("common:status.primary")}</Badge>
                ) : null}
              </div>
              {canWrite ? (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="sm">
                      {t("actions.actions_menu_aria")}
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => setEditing(p)}>
                      {t("common:actions.edit")}
                    </DropdownMenuItem>
                    {!p.is_primary ? (
                      <DropdownMenuItem onClick={() => handleSetPrimary(p.id)}>
                        {t("actions.set_as_primary")}
                      </DropdownMenuItem>
                    ) : null}
                    <DropdownMenuItem
                      className="text-destructive"
                      onClick={() => setDeletingId(p.id)}
                    >
                      {t("common:actions.remove")}
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : null}
            </li>
          ))}
        </ActivityList>
      )}

      {addOpen ? (
        <PhoneFormDialog
          mode="create"
          contactId={contact.id}
          open={addOpen}
          onOpenChange={setAddOpen}
        />
      ) : null}
      {editing ? (
        <PhoneFormDialog
          mode="edit"
          contactId={contact.id}
          phone={editing}
          open={!!editing}
          onOpenChange={(o) => !o && setEditing(null)}
        />
      ) : null}
      {deletingId != null ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setDeletingId(null)}
          onConfirm={handleDelete}
          title={t("confirm.remove_phone_title")}
          description={t("confirm.remove_phone_body")}
          confirmLabel={t("common:actions.remove")}
          destructive
          busy={deletePhone.isPending}
        />
      ) : null}
    </Section>
  );
}

function TagsSection({ contact, canWrite }: { contact: Contact; canWrite: boolean }) {
  const { t } = useTranslation("contacts");
  const [editOpen, setEditOpen] = useState(false);
  const tags = contact.tags ?? [];

  const editButton = canWrite ? (
    <Button size="sm" variant="outline" onClick={() => setEditOpen(true)}>
      {t("actions.edit_tags")}
    </Button>
  ) : (
    <Tooltip>
      <TooltipTrigger asChild>
        <span>
          <Button size="sm" variant="outline" disabled>
            {t("actions.edit_tags")}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>{t("common:tooltips.reservations_role_required")}</TooltipContent>
    </Tooltip>
  );

  return (
    <Section title={t("headings.tags")}>
      <div className="flex items-center justify-end">{editButton}</div>
      {tags.length === 0 ? <EmptyState title={t("empty.tags")} /> : <TagChips tags={tags} />}

      {editOpen ? (
        <TagsFormDialog
          contactId={contact.id}
          tags={tags}
          open={editOpen}
          onOpenChange={setEditOpen}
        />
      ) : null}
    </Section>
  );
}

// GAP-042: address is collapsible — the owner noted it "could be hidden … useful
// to have it there". Collapsed by default so the profile leads with identity.
function AddressSection({ contact }: { contact: Contact }) {
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

export function DetailsTab() {
  const { t } = useTranslation("contacts");
  const { contact } = useOutletContext<ContactOutletContext>();
  const canWrite = useHasReservationsRole();

  return (
    <div className="space-y-8 p-6">
      <Section title={t("headings.overview")}>
        <FactList>
          <FactRow label={t("fields.title")} value={contact.title || "—"} />
          <FactRow label={t("fields.first_name")} value={contact.first_name || "—"} />
          <FactRow label={t("fields.last_name")} value={contact.last_name || "—"} />
          <FactRow label={t("fields.agency")} value={contact.agency_detail?.name || "—"} />
          <FactRow
            label={t("fields.website")}
            value={
              contact.website_url ? (
                <a
                  href={contact.website_url}
                  target="_blank"
                  rel="noreferrer"
                  className="hover:underline"
                >
                  {contact.website_url}
                </a>
              ) : (
                "—"
              )
            }
          />
          <FactRow label={t("fields.preferred_method")} value={contact.preferred_method || "—"} />
          <FactRow
            label={t("fields.notes")}
            value={
              contact.notes ? <span className="whitespace-pre-line">{contact.notes}</span> : "—"
            }
          />
        </FactList>
      </Section>

      <AddressSection contact={contact} />

      <EmailsSection contact={contact} canWrite={canWrite} />
      <PhonesSection contact={contact} canWrite={canWrite} />
      <TagsSection contact={contact} canWrite={canWrite} />
      <LinkedContactsAccordion contactId={contact.id} />
      <ContactEnquiryHistory contactId={contact.id} />
      <ContactBookingHistory contactId={contact.id} />
    </div>
  );
}
