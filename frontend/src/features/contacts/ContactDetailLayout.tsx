import { useState } from "react";
import { NavLink, Outlet, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/PageHeader";
import { TwoColumn } from "@/components/layout/TwoColumn";
import { StatusBadge } from "@/components/data/StatusBadge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ErrorState } from "@/components/feedback/ErrorState";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { cn } from "@/lib/cn";
import { ApiError } from "@/lib/api/errors";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { useContact, useDeleteContact } from "./hooks";
import { contactDisplayName } from "./display";
import { ContactFormDialog } from "./components/ContactFormDialog";
import type { Contact } from "./schemas";

export const CONTACT_TABS = [
  { slug: "details", label: "Details" },
  { slug: "properties", label: "Properties" },
  { slug: "notes", label: "Notes" },
  { slug: "audit", label: "Audit" },
] as const;

export interface ContactOutletContext {
  contact: Contact;
}

function HeaderActions({ contact }: { contact: Contact }) {
  const navigate = useNavigate();
  const canWrite = useHasReservationsRole();
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const deleteMutation = useDeleteContact(contact.id);

  const handleDelete = async () => {
    try {
      await deleteMutation.mutateAsync();
      toast.success("Contact deleted");
      navigate("/contacts");
    } catch (error) {
      const message = error instanceof ApiError ? error.detail : "Something went wrong";
      toast.error(message);
    }
  };

  const editButton = canWrite ? (
    <Button variant="outline" size="sm" onClick={() => setEditOpen(true)}>
      Edit
    </Button>
  ) : (
    <Tooltip>
      <TooltipTrigger asChild>
        <span>
          <Button variant="outline" size="sm" disabled>
            Edit
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>Reservations role required</TooltipContent>
    </Tooltip>
  );

  const deleteButton = canWrite ? (
    <Button variant="destructive" size="sm" onClick={() => setDeleteOpen(true)}>
      Delete
    </Button>
  ) : (
    <Tooltip>
      <TooltipTrigger asChild>
        <span>
          <Button variant="destructive" size="sm" disabled>
            Delete
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>Reservations role required</TooltipContent>
    </Tooltip>
  );

  return (
    <>
      {editButton}
      {deleteButton}
      {editOpen ? (
        <ContactFormDialog
          mode="edit"
          contactId={contact.id}
          contact={contact}
          open={editOpen}
          onOpenChange={setEditOpen}
        />
      ) : null}
      {deleteOpen ? (
        <ConfirmDialog
          open={deleteOpen}
          onOpenChange={setDeleteOpen}
          onConfirm={handleDelete}
          title="Delete this contact?"
          description="This will permanently remove the contact and their email/phone records."
          confirmLabel="Delete"
          destructive
          busy={deleteMutation.isPending}
        />
      ) : null}
    </>
  );
}

function RailSummary({ contact }: { contact: Contact }) {
  const name = contactDisplayName(contact);
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-foreground text-lg font-semibold">{name}</h2>
        {contact.company && (contact.first_name || contact.last_name) ? (
          <p className="text-muted-foreground text-sm">{contact.company}</p>
        ) : null}
      </div>
      {contact.status ? <StatusBadge status={contact.status} /> : null}
    </div>
  );
}

export function ContactDetailLayout() {
  const { id } = useParams<{ id: string }>();
  const query = useContact(id);

  if (query.isLoading) {
    return (
      <div className="space-y-4 p-6">
        <Skeleton className="h-8 w-1/3" />
        <Skeleton className="h-4 w-1/4" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (query.isError || !query.data) {
    const is404 = query.error instanceof ApiError && query.error.status === 404;
    return (
      <div className="p-6">
        <ErrorState
          title={is404 ? "Contact not found" : "Couldn't load this contact"}
          description={
            is404
              ? "It may have been deleted or you may not have access."
              : "Try again or head back to the list."
          }
          onRetry={is404 ? undefined : () => query.refetch()}
        />
      </div>
    );
  }

  const contact = query.data;
  const name = contactDisplayName(contact);

  return (
    <div>
      <PageHeader
        title={name}
        subtitle={
          contact.company && (contact.first_name || contact.last_name) ? contact.company : undefined
        }
        breadcrumbs={[{ label: "Contacts", to: "/contacts" }, { label: name }]}
        actions={<HeaderActions contact={contact} />}
      />

      <div className="border-border border-b px-6">
        <nav className="flex gap-1" aria-label="Contact sections">
          {CONTACT_TABS.map((tab) => (
            <NavLink
              key={tab.slug}
              to={tab.slug}
              className={({ isActive }) =>
                cn(
                  "border-b-2 px-3 py-2 text-sm font-medium",
                  isActive
                    ? "border-foreground text-foreground"
                    : "text-muted-foreground hover:text-foreground border-transparent",
                )
              }
            >
              {tab.label}
            </NavLink>
          ))}
        </nav>
      </div>

      <TwoColumn rightRail={<RailSummary contact={contact} />}>
        <Outlet context={{ contact } satisfies ContactOutletContext} />
      </TwoColumn>
    </div>
  );
}
