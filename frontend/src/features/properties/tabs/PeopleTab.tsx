import { useOutletContext } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Section } from "@/components/data/Section";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { formatDate } from "@/lib/format/date";
import { useContact, usePropertyContacts } from "../hooks";
import type { Contact, PropertyContactAssignment, PropertyDetail } from "../schemas";

interface PeopleContext {
  property: PropertyDetail;
}

function displayName(contact: Contact | undefined, fallbackId: number): string {
  if (!contact) return `Contact #${fallbackId}`;
  const full = [contact.first_name, contact.last_name].filter(Boolean).join(" ").trim();
  if (full) return full;
  if (contact.company) return contact.company;
  return `Contact #${contact.id}`;
}

function primaryEmail(contact: Contact | undefined): string | null {
  if (!contact?.emails?.length) return null;
  const primary = contact.emails.find((e) => e.is_primary);
  return (primary ?? contact.emails[0]).email;
}

function AssignmentRow({ assignment }: { assignment: PropertyContactAssignment }) {
  const contact = useContact(assignment.contact);
  const dateRange =
    assignment.start_date || assignment.end_date
      ? `${formatDate(assignment.start_date)} – ${formatDate(assignment.end_date)}`
      : null;

  return (
    <li className="flex items-center justify-between gap-4 px-4 py-3 text-sm">
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
      </div>
    </li>
  );
}

function AssignmentsList({ assignments }: { assignments: PropertyContactAssignment[] }) {
  return (
    <ul className="border-border bg-card divide-border divide-y rounded-lg border">
      {assignments.map((a) => (
        <AssignmentRow key={a.id} assignment={a} />
      ))}
    </ul>
  );
}

export function PeopleTab() {
  const { property } = useOutletContext<PeopleContext>();
  const propertyKey = property.slug || property.id;
  const contacts = usePropertyContacts(propertyKey);

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

  if (rows.length === 0) {
    return (
      <div className="p-6">
        <EmptyState title="No contacts assigned" />
      </div>
    );
  }

  return (
    <div className="space-y-8 p-6">
      <Section title="Active assignments">
        {active.length === 0 ? (
          <EmptyState title="No active assignments" />
        ) : (
          <AssignmentsList assignments={active} />
        )}
      </Section>
      {ended.length > 0 ? (
        <Section title="Ended assignments">
          <AssignmentsList assignments={ended} />
        </Section>
      ) : null}
    </div>
  );
}
