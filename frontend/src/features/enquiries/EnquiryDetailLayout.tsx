import { useState } from "react";
import { NavLink, Outlet, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/PageHeader";
import { TwoColumn } from "@/components/layout/TwoColumn";
import { StatusBadge } from "@/components/data/StatusBadge";
import { FactList, FactRow } from "@/components/data/FactList";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";
import { ActionButton } from "@/components/feedback/ActionButton";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/format/date";
import { ApiError } from "@/lib/api/errors";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { useEnquiry, useReopenEnquiry } from "./hooks";
import { AssignDialog } from "./components/AssignDialog";
import { CloseDialog } from "./components/CloseDialog";
import { ENQUIRY_SOURCE_LABELS, ENQUIRY_STATUS_LABELS, type EnquiryDetail } from "./schemas";

export const ENQUIRY_TABS = [
  { slug: "details", label: "Details" },
  { slug: "activity", label: "Activity" },
  { slug: "notes", label: "Notes" },
] as const;

export interface EnquiryOutletContext {
  enquiry: EnquiryDetail;
}

type DialogKind = "assign" | "close" | "reopen" | null;

function guestName(enq: EnquiryDetail): string {
  const name = `${enq.first_name ?? ""} ${enq.last_name ?? ""}`.trim();
  return name || enq.email || enq.reference;
}

interface EnquiryActionsProps {
  enquiry: EnquiryDetail;
  onOpen: (dialog: DialogKind) => void;
}

function EnquiryActions({ enquiry, onOpen }: EnquiryActionsProps) {
  const navigate = useNavigate();
  const hasRole = useHasReservationsRole();

  const isClosed = enquiry.status === "lost";
  const isFinal = enquiry.status === "converted" || enquiry.status === "lost";

  const handleConvertClick = () => {
    navigate(`/quotations/new?enquiry=${enquiry.id}`);
  };

  return (
    <div className="space-y-2">
      <p className="text-muted-foreground text-xs font-semibold tracking-wider uppercase">
        Actions
      </p>
      <ActionButton
        label="Assign…"
        onClick={() => onOpen("assign")}
        disableReason={hasRole ? null : "Reservations role required."}
      />
      <ActionButton
        label="Convert to quote"
        onClick={handleConvertClick}
        disableReason={
          !hasRole
            ? "Reservations role required."
            : isFinal
              ? "Not available for this status."
              : null
        }
      />
      <ActionButton
        label="Close as lost…"
        onClick={() => onOpen("close")}
        disableReason={
          !hasRole ? "Reservations role required." : isFinal ? "Already closed or converted." : null
        }
      />
      <ActionButton
        label="Reopen"
        onClick={() => onOpen("reopen")}
        disableReason={
          !hasRole
            ? "Reservations role required."
            : !isClosed
              ? "Only available for closed enquiries."
              : null
        }
      />
    </div>
  );
}

interface RailProps {
  enquiry: EnquiryDetail;
  onOpenDialog: (dialog: DialogKind) => void;
}

function RailSummary({ enquiry, onOpenDialog }: RailProps) {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-foreground text-lg font-semibold">{enquiry.reference}</h2>
        <p className="text-muted-foreground text-sm">{guestName(enquiry)}</p>
      </div>
      <StatusBadge status={ENQUIRY_STATUS_LABELS[enquiry.status]} />
      <FactList>
        <FactRow
          label="Dates"
          value={
            enquiry.date_from || enquiry.date_to
              ? `${formatDate(enquiry.date_from ?? null)} – ${formatDate(enquiry.date_to ?? null)}`
              : "Flexible"
          }
        />
        <FactRow
          label="Party"
          value={`${enquiry.adults}A${enquiry.children ? ` · ${enquiry.children}C` : ""}`}
        />
        <FactRow label="Source" value={ENQUIRY_SOURCE_LABELS[enquiry.site_source]} />
        <FactRow label="Property" value={enquiry.property != null ? `#${enquiry.property}` : "—"} />
        <FactRow
          label="Assigned"
          value={enquiry.assigned_to != null ? `User #${enquiry.assigned_to}` : "Unassigned"}
        />
      </FactList>
      <EnquiryActions enquiry={enquiry} onOpen={onOpenDialog} />
    </div>
  );
}

export function EnquiryDetailLayout() {
  const { id } = useParams<{ id: string }>();
  const query = useEnquiry(id);
  const [dialog, setDialog] = useState<DialogKind>(null);
  const reopenMutation = useReopenEnquiry(id ?? 0);

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
          title={is404 ? "Enquiry not found" : "Couldn't load this enquiry"}
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

  const enquiry = query.data;

  const handleReopen = async () => {
    try {
      await reopenMutation.mutateAsync("");
      toast.success("Enquiry reopened");
      setDialog(null);
    } catch (error) {
      const message = error instanceof ApiError ? error.detail : "Couldn't reopen enquiry";
      toast.error(message);
    }
  };

  return (
    <div>
      <PageHeader
        title={enquiry.reference}
        subtitle={guestName(enquiry)}
        breadcrumbs={[{ label: "Enquiries", to: "/enquiries" }, { label: enquiry.reference }]}
      />

      <div className="border-border border-b px-6">
        <nav className="flex gap-1" aria-label="Enquiry sections">
          {ENQUIRY_TABS.map((tab) => (
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

      <TwoColumn rightRail={<RailSummary enquiry={enquiry} onOpenDialog={setDialog} />}>
        <Outlet context={{ enquiry } satisfies EnquiryOutletContext} />
      </TwoColumn>

      {dialog === "assign" && (
        <AssignDialog
          enquiryId={enquiry.id}
          currentUserId={enquiry.assigned_to ?? null}
          open={true}
          onOpenChange={(open) => {
            if (!open) setDialog(null);
          }}
        />
      )}
      {dialog === "close" && (
        <CloseDialog
          enquiryId={enquiry.id}
          open={true}
          onOpenChange={(open) => {
            if (!open) setDialog(null);
          }}
        />
      )}
      <ConfirmDialog
        open={dialog === "reopen"}
        onOpenChange={(open) => {
          if (!open) setDialog(null);
        }}
        onConfirm={handleReopen}
        title="Reopen this enquiry?"
        description="It will move back to New."
        confirmLabel="Reopen"
        busy={reopenMutation.isPending}
      />
    </div>
  );
}
