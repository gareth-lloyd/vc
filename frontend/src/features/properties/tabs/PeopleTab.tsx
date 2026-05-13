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
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Section } from "@/components/data/Section";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { formatDate } from "@/lib/format/date";
import { ApiError } from "@/lib/api/errors";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { useDeletePropertyContact, usePropertyContacts } from "../hooks";
import {
  useContact,
  useDeleteContactEmail,
  useDeleteContactPhone,
  useSetPrimaryContactEmail,
  useSetPrimaryContactPhone,
} from "@/features/contacts/hooks";
import type { Contact, ContactEmail, ContactPhone } from "@/features/contacts/schemas";
import { contactDisplayName } from "@/features/contacts/display";
import { ContactFormDialog } from "@/features/contacts/components/ContactFormDialog";
import { EmailFormDialog } from "@/features/contacts/components/EmailFormDialog";
import { PhoneFormDialog } from "@/features/contacts/components/PhoneFormDialog";
import type { PropertyContactAssignment, PropertyDetail } from "../schemas";
import { AssignmentFormDialog } from "../components/AssignmentFormDialog";

interface PeopleContext {
  property: PropertyDetail;
}

function displayName(contact: Contact | undefined, fallbackId: number): string {
  if (!contact) return `Contact #${fallbackId}`;
  return contactDisplayName(contact);
}

function primaryEmail(contact: Contact | undefined): string | null {
  if (!contact?.emails?.length) return null;
  const primary = contact.emails.find((e) => e.is_primary);
  return (primary ?? contact.emails[0]).email;
}

function EmailList({
  emails,
  contactId,
  canWrite,
}: {
  emails: ContactEmail[];
  contactId: number;
  canWrite: boolean;
}) {
  const [addOpen, setAddOpen] = useState(false);
  const [editing, setEditing] = useState<ContactEmail | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const setPrimary = useSetPrimaryContactEmail(contactId);
  const deleteEmail = useDeleteContactEmail(contactId);

  const handleDelete = async () => {
    if (deletingId == null) return;
    try {
      await deleteEmail.mutateAsync({ emailId: deletingId });
      toast.success("Email removed");
      setDeletingId(null);
    } catch {
      toast.error("Failed to remove email");
    }
  };

  const handleSetPrimary = async (emailId: number) => {
    try {
      await setPrimary.mutateAsync({ emailId });
    } catch {
      toast.error("Failed to set primary");
    }
  };

  return (
    <>
      <div className="mt-1 space-y-1">
        {emails.map((e) => (
          <div key={e.id} className="flex items-center gap-2 text-xs">
            <span className="text-muted-foreground truncate">{e.email}</span>
            {e.label ? (
              <span className="text-muted-foreground/60 text-[10px] uppercase">{e.label}</span>
            ) : null}
            {e.is_primary ? (
              <Badge variant="outline" className="text-[10px]">
                Primary
              </Badge>
            ) : null}
            {canWrite ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="sm" className="h-5 w-5 p-0">
                    ···
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
          </div>
        ))}
        {canWrite ? (
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-1 text-xs"
            onClick={() => setAddOpen(true)}
          >
            + Add email
          </Button>
        ) : null}
      </div>

      {addOpen ? (
        <EmailFormDialog
          contactId={contactId}
          open={addOpen}
          onOpenChange={setAddOpen}
          mode="create"
        />
      ) : null}
      {editing ? (
        <EmailFormDialog
          contactId={contactId}
          open={!!editing}
          onOpenChange={(o) => !o && setEditing(null)}
          mode="edit"
          email={editing}
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
    </>
  );
}

function PhoneList({
  phones,
  contactId,
  canWrite,
}: {
  phones: ContactPhone[];
  contactId: number;
  canWrite: boolean;
}) {
  const [addOpen, setAddOpen] = useState(false);
  const [editing, setEditing] = useState<ContactPhone | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const setPrimary = useSetPrimaryContactPhone(contactId);
  const deletePhone = useDeleteContactPhone(contactId);

  const handleDelete = async () => {
    if (deletingId == null) return;
    try {
      await deletePhone.mutateAsync({ phoneId: deletingId });
      toast.success("Phone removed");
      setDeletingId(null);
    } catch {
      toast.error("Failed to remove phone");
    }
  };

  const handleSetPrimary = async (phoneId: number) => {
    try {
      await setPrimary.mutateAsync({ phoneId });
    } catch {
      toast.error("Failed to set primary");
    }
  };

  return (
    <>
      <div className="mt-1 space-y-1">
        {phones.map((p) => (
          <div key={p.id} className="flex items-center gap-2 text-xs">
            <span className="text-muted-foreground truncate">{p.number}</span>
            {p.label ? (
              <span className="text-muted-foreground/60 text-[10px] uppercase">{p.label}</span>
            ) : null}
            {p.is_primary ? (
              <Badge variant="outline" className="text-[10px]">
                Primary
              </Badge>
            ) : null}
            {canWrite ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="sm" className="h-5 w-5 p-0">
                    ···
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
          </div>
        ))}
        {canWrite ? (
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-1 text-xs"
            onClick={() => setAddOpen(true)}
          >
            + Add phone
          </Button>
        ) : null}
      </div>

      {addOpen ? (
        <PhoneFormDialog
          contactId={contactId}
          open={addOpen}
          onOpenChange={setAddOpen}
          mode="create"
        />
      ) : null}
      {editing ? (
        <PhoneFormDialog
          contactId={contactId}
          open={!!editing}
          onOpenChange={(o) => !o && setEditing(null)}
          mode="edit"
          phone={editing}
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
    </>
  );
}

function AssignmentRow({
  assignment,
  propertyId,
  canWrite,
}: {
  assignment: PropertyContactAssignment;
  propertyId: string | number;
  canWrite: boolean;
}) {
  const contact = useContact(assignment.contact);
  const [editOpen, setEditOpen] = useState(false);
  const [editContactOpen, setEditContactOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const deleteMutation = useDeletePropertyContact(propertyId);
  const dateRange =
    assignment.start_date || assignment.end_date
      ? `${formatDate(assignment.start_date)} – ${formatDate(assignment.end_date)}`
      : null;

  const handleDelete = async () => {
    try {
      await deleteMutation.mutateAsync({ mappingId: assignment.id });
      toast.success("Contact removed from property");
      setDeleteOpen(false);
    } catch (error) {
      if (error instanceof ApiError) {
        toast.error(error.detail);
      } else {
        toast.error("Failed to remove contact");
      }
    }
  };

  return (
    <li className="px-4 py-3 text-sm">
      <div className="flex items-center justify-between gap-4">
        <div className="flex min-w-0 flex-col">
          {contact.isLoading ? (
            <Skeleton className="h-4 w-32" />
          ) : (
            <span className="text-foreground truncate font-medium">
              {displayName(contact.data, assignment.contact)}
            </span>
          )}
          <span className="text-muted-foreground text-xs">{primaryEmail(contact.data) ?? "—"}</span>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span className="text-muted-foreground capitalize">
            {assignment.role?.replace(/_/g, " ") ?? "—"}
          </span>
          {assignment.is_primary ? <Badge variant="secondary">Primary</Badge> : null}
          {dateRange ? <span className="text-muted-foreground">{dateRange}</span> : null}
          {canWrite ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm" className="h-6 px-2">
                  Actions
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => setEditOpen(true)}>
                  Edit assignment
                </DropdownMenuItem>
                {contact.data ? (
                  <DropdownMenuItem onClick={() => setEditContactOpen(true)}>
                    Edit contact
                  </DropdownMenuItem>
                ) : null}
                <DropdownMenuItem className="text-destructive" onClick={() => setDeleteOpen(true)}>
                  Remove
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null}
        </div>
      </div>

      {contact.data ? (
        <div className="mt-2 ml-0 grid grid-cols-2 gap-4">
          <div>
            <span className="text-muted-foreground text-[10px] font-semibold uppercase">
              Emails
            </span>
            <EmailList
              emails={contact.data.emails}
              contactId={contact.data.id}
              canWrite={canWrite}
            />
          </div>
          <div>
            <span className="text-muted-foreground text-[10px] font-semibold uppercase">
              Phones
            </span>
            <PhoneList
              phones={contact.data.phones}
              contactId={contact.data.id}
              canWrite={canWrite}
            />
          </div>
        </div>
      ) : null}

      {editOpen && contact.data ? (
        <AssignmentFormDialog
          propertyId={propertyId}
          open={editOpen}
          onOpenChange={setEditOpen}
          mode="edit"
          assignment={assignment}
          contact={contact.data}
        />
      ) : null}
      {editContactOpen && contact.data ? (
        <ContactFormDialog
          open={editContactOpen}
          onOpenChange={setEditContactOpen}
          mode="edit"
          contactId={contact.data.id}
          contact={contact.data}
        />
      ) : null}
      {deleteOpen ? (
        <ConfirmDialog
          open
          onOpenChange={setDeleteOpen}
          onConfirm={handleDelete}
          title="Remove contact from property?"
          description="This only removes the assignment — the contact itself won't be deleted."
          confirmLabel="Remove"
          destructive
          busy={deleteMutation.isPending}
        />
      ) : null}
    </li>
  );
}

function AssignmentsList({
  assignments,
  propertyId,
  canWrite,
}: {
  assignments: PropertyContactAssignment[];
  propertyId: string | number;
  canWrite: boolean;
}) {
  return (
    <ul className="border-border bg-card divide-border divide-y rounded-lg border">
      {assignments.map((a) => (
        <AssignmentRow key={a.id} assignment={a} propertyId={propertyId} canWrite={canWrite} />
      ))}
    </ul>
  );
}

export function PeopleTab() {
  const { property } = useOutletContext<PeopleContext>();
  const propertyKey = property.slug || property.id;
  const contacts = usePropertyContacts(propertyKey);
  const canWrite = useHasReservationsRole();

  const [addOpen, setAddOpen] = useState(false);
  const [createContactOpen, setCreateContactOpen] = useState(false);

  if (contacts.isLoading) {
    return (
      <div className="space-y-4 p-6">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (contacts.isError) {
    return (
      <div className="p-6">
        <ErrorState
          title="Couldn't load people"
          description="Try again."
          onRetry={() => contacts.refetch()}
        />
      </div>
    );
  }

  const rows = contacts.data?.results ?? [];
  const active = rows.filter((a) => !a.end_date);
  const ended = rows.filter((a) => !!a.end_date);

  return (
    <div className="space-y-8 p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">People</h2>
        {canWrite ? (
          <Button size="sm" onClick={() => setAddOpen(true)}>
            Add contact
          </Button>
        ) : (
          <Tooltip>
            <TooltipTrigger asChild>
              <span>
                <Button size="sm" disabled>
                  Add contact
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent>You need the Reservations role to add contacts</TooltipContent>
          </Tooltip>
        )}
      </div>

      {rows.length === 0 ? (
        <EmptyState title="No contacts assigned" />
      ) : (
        <>
          <Section title="Active assignments">
            {active.length === 0 ? (
              <EmptyState title="No active assignments" />
            ) : (
              <AssignmentsList assignments={active} propertyId={propertyKey} canWrite={canWrite} />
            )}
          </Section>
          {ended.length > 0 ? (
            <Section title="Ended assignments">
              <AssignmentsList assignments={ended} propertyId={propertyKey} canWrite={canWrite} />
            </Section>
          ) : null}
        </>
      )}

      {addOpen ? (
        <AssignmentFormDialog
          propertyId={propertyKey}
          open={addOpen}
          onOpenChange={setAddOpen}
          mode="create"
          onCreateNewContact={() => {
            setAddOpen(false);
            setCreateContactOpen(true);
          }}
        />
      ) : null}
      {createContactOpen ? (
        <ContactFormDialog
          open={createContactOpen}
          onOpenChange={setCreateContactOpen}
          mode="create"
          onCreated={() => {
            setAddOpen(true);
          }}
        />
      ) : null}
    </div>
  );
}
