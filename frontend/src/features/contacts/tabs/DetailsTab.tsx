import { useState } from "react";
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
import type { Contact, ContactEmail, ContactPhone } from "../schemas";
import type { ContactOutletContext } from "../ContactDetailLayout";

function EmailsSection({ contact, canWrite }: { contact: Contact; canWrite: boolean }) {
  const [addOpen, setAddOpen] = useState(false);
  const [editing, setEditing] = useState<ContactEmail | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const setPrimary = useSetPrimaryContactEmail(contact.id);
  const deleteEmail = useDeleteContactEmail(contact.id);

  const handleDelete = async () => {
    if (deletingId == null) return;
    try {
      await deleteEmail.mutateAsync({ emailId: deletingId });
      toast.success("Email removed");
      setDeletingId(null);
    } catch (error) {
      const message = error instanceof ApiError ? error.detail : "Failed to remove email";
      toast.error(message);
    }
  };

  const handleSetPrimary = async (emailId: number) => {
    try {
      await setPrimary.mutateAsync({ emailId });
    } catch {
      toast.error("Failed to set primary");
    }
  };

  const addButton = canWrite ? (
    <Button size="sm" variant="outline" onClick={() => setAddOpen(true)}>
      Add email
    </Button>
  ) : (
    <Tooltip>
      <TooltipTrigger asChild>
        <span>
          <Button size="sm" variant="outline" disabled>
            Add email
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>Reservations role required</TooltipContent>
    </Tooltip>
  );

  return (
    <Section title="Emails">
      <div className="flex items-center justify-end">{addButton}</div>
      {contact.emails.length === 0 ? (
        <EmptyState title="No emails yet" />
      ) : (
        <ul className="border-border bg-card divide-border divide-y rounded-lg border">
          {contact.emails.map((e) => (
            <li key={e.id} className="flex items-center justify-between gap-4 px-4 py-3 text-sm">
              <div className="flex min-w-0 items-center gap-2">
                <span className="text-foreground truncate">{e.email}</span>
                {e.label ? (
                  <span className="text-muted-foreground/70 text-xs uppercase">{e.label}</span>
                ) : null}
                {e.is_primary ? <Badge variant="outline">Primary</Badge> : null}
              </div>
              {canWrite ? (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="sm">
                      Actions
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => setEditing(e)}>Edit</DropdownMenuItem>
                    {!e.is_primary ? (
                      <DropdownMenuItem onClick={() => handleSetPrimary(e.id)}>
                        Set as primary
                      </DropdownMenuItem>
                    ) : null}
                    <DropdownMenuItem
                      className="text-destructive"
                      onClick={() => setDeletingId(e.id)}
                    >
                      Remove
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : null}
            </li>
          ))}
        </ul>
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
          title="Remove email?"
          description="This email address will be permanently removed from this contact."
          confirmLabel="Remove"
          destructive
          busy={deleteEmail.isPending}
        />
      ) : null}
    </Section>
  );
}

function PhonesSection({ contact, canWrite }: { contact: Contact; canWrite: boolean }) {
  const [addOpen, setAddOpen] = useState(false);
  const [editing, setEditing] = useState<ContactPhone | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const setPrimary = useSetPrimaryContactPhone(contact.id);
  const deletePhone = useDeleteContactPhone(contact.id);

  const handleDelete = async () => {
    if (deletingId == null) return;
    try {
      await deletePhone.mutateAsync({ phoneId: deletingId });
      toast.success("Phone removed");
      setDeletingId(null);
    } catch (error) {
      const message = error instanceof ApiError ? error.detail : "Failed to remove phone";
      toast.error(message);
    }
  };

  const handleSetPrimary = async (phoneId: number) => {
    try {
      await setPrimary.mutateAsync({ phoneId });
    } catch {
      toast.error("Failed to set primary");
    }
  };

  const addButton = canWrite ? (
    <Button size="sm" variant="outline" onClick={() => setAddOpen(true)}>
      Add phone
    </Button>
  ) : (
    <Tooltip>
      <TooltipTrigger asChild>
        <span>
          <Button size="sm" variant="outline" disabled>
            Add phone
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>Reservations role required</TooltipContent>
    </Tooltip>
  );

  return (
    <Section title="Phones">
      <div className="flex items-center justify-end">{addButton}</div>
      {contact.phones.length === 0 ? (
        <EmptyState title="No phones yet" />
      ) : (
        <ul className="border-border bg-card divide-border divide-y rounded-lg border">
          {contact.phones.map((p) => (
            <li key={p.id} className="flex items-center justify-between gap-4 px-4 py-3 text-sm">
              <div className="flex min-w-0 items-center gap-2">
                <span className="text-foreground truncate">{p.number}</span>
                {p.label ? (
                  <span className="text-muted-foreground/70 text-xs uppercase">{p.label}</span>
                ) : null}
                {p.is_primary ? <Badge variant="outline">Primary</Badge> : null}
              </div>
              {canWrite ? (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="sm">
                      Actions
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => setEditing(p)}>Edit</DropdownMenuItem>
                    {!p.is_primary ? (
                      <DropdownMenuItem onClick={() => handleSetPrimary(p.id)}>
                        Set as primary
                      </DropdownMenuItem>
                    ) : null}
                    <DropdownMenuItem
                      className="text-destructive"
                      onClick={() => setDeletingId(p.id)}
                    >
                      Remove
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : null}
            </li>
          ))}
        </ul>
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
          title="Remove phone?"
          description="This phone number will be permanently removed from this contact."
          confirmLabel="Remove"
          destructive
          busy={deletePhone.isPending}
        />
      ) : null}
    </Section>
  );
}

export function DetailsTab() {
  const { contact } = useOutletContext<ContactOutletContext>();
  const canWrite = useHasReservationsRole();

  return (
    <div className="space-y-8 p-6">
      <Section title="Overview">
        <FactList>
          <FactRow label="Title" value={contact.title || "—"} />
          <FactRow label="First name" value={contact.first_name || "—"} />
          <FactRow label="Last name" value={contact.last_name || "—"} />
          <FactRow label="Company" value={contact.company || "—"} />
          <FactRow
            label="Website"
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
          <FactRow label="Preferred method" value={contact.preferred_method || "—"} />
          <FactRow label="Address line 1" value={contact.address_line_1 || "—"} />
          <FactRow label="Address line 2" value={contact.address_line_2 || "—"} />
          <FactRow
            label="Notes"
            value={
              contact.notes ? <span className="whitespace-pre-line">{contact.notes}</span> : "—"
            }
          />
        </FactList>
      </Section>

      <EmailsSection contact={contact} canWrite={canWrite} />
      <PhonesSection contact={contact} canWrite={canWrite} />
    </div>
  );
}
