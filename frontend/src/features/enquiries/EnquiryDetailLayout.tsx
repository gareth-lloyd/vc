import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { ChevronDown, ChevronRight } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/PageHeader";
import { TwoColumn } from "@/components/layout/TwoColumn";
import { StatusBadge } from "@/components/data/StatusBadge";
import { FactList, FactRow } from "@/components/data/FactList";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { ActionButton } from "@/components/feedback/ActionButton";
import { formatDate } from "@/lib/format/date";
import { ApiError } from "@/lib/api/errors";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { useEnquiry, useReopenEnquiry } from "./hooks";
import { AssignDialog } from "./components/AssignDialog";
import { CloseDialog } from "./components/CloseDialog";
import { EnquiryQuoteStack } from "./components/EnquiryQuoteStack";
import { QuoteBuilder } from "@/features/quotations/components/QuoteBuilder";
import { DetailsTab } from "./tabs/DetailsTab";
import { ActivityTab } from "./tabs/ActivityTab";
import { NotesTab } from "./tabs/NotesTab";
import { enquirySourceLabel, enquiryStatusLabel, type EnquiryDetail } from "./schemas";

type DialogKind = "assign" | "close" | "reopen" | null;

function guestName(enq: EnquiryDetail): string {
  if (enq.guest_name) return enq.guest_name;
  const denorm = `${enq.first_name ?? ""} ${enq.last_name ?? ""}`.trim();
  return denorm || enq.email || enq.reference;
}

interface EnquiryActionsProps {
  enquiry: EnquiryDetail;
  onOpen: (dialog: DialogKind) => void;
}

function EnquiryActions({ enquiry, onOpen }: EnquiryActionsProps) {
  const { t } = useTranslation("enquiries");
  const hasRole = useHasReservationsRole();

  const isClosed = enquiry.status === "lost";
  const isFinal = enquiry.status === "converted" || enquiry.status === "lost";
  const roleRequired = t("common:errors.reservations_role_required");

  return (
    <div className="space-y-2">
      <p className="text-muted-foreground text-xs font-semibold tracking-wider uppercase">
        {t("detail.rail.actions_heading")}
      </p>
      <ActionButton
        label={t("detail.actions.assign")}
        onClick={() => onOpen("assign")}
        disableReason={hasRole ? null : roleRequired}
      />
      <ActionButton
        label={t("detail.actions.close")}
        onClick={() => onOpen("close")}
        disableReason={
          !hasRole ? roleRequired : isFinal ? t("detail.actions.close_disabled_state") : null
        }
      />
      <ActionButton
        label={t("detail.actions.reopen")}
        onClick={() => onOpen("reopen")}
        disableReason={
          !hasRole ? roleRequired : !isClosed ? t("detail.actions.reopen_disabled_state") : null
        }
      />
    </div>
  );
}

function RailSummary({
  enquiry,
  onOpenDialog,
}: {
  enquiry: EnquiryDetail;
  onOpenDialog: (dialog: DialogKind) => void;
}) {
  const { t } = useTranslation("enquiries");
  const partyText =
    enquiry.children > 0
      ? t("detail.rail.party_format_with_children", {
          adults: enquiry.adults,
          children: enquiry.children,
        })
      : t("detail.rail.party_format", { adults: enquiry.adults });

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-foreground font-serif text-lg font-semibold">{guestName(enquiry)}</h2>
        <p className="text-muted-foreground font-mono text-xs">{enquiry.reference}</p>
      </div>
      <StatusBadge status={enquiryStatusLabel(enquiry.status)} />
      <FactList>
        <FactRow
          label={t("detail.rail.dates")}
          value={
            enquiry.date_from || enquiry.date_to
              ? `${formatDate(enquiry.date_from ?? null)} – ${formatDate(enquiry.date_to ?? null)}`
              : t("detail.rail.flexible")
          }
        />
        <FactRow label={t("detail.rail.party")} value={partyText} />
        <FactRow label={t("detail.rail.source")} value={enquirySourceLabel(enquiry.site_source)} />
        <FactRow
          label={t("detail.rail.property")}
          value={
            enquiry.property_name ??
            (enquiry.property != null
              ? t("detail.rail.property_with_id", { id: enquiry.property })
              : "—")
          }
        />
        <FactRow
          label={t("detail.rail.assigned")}
          value={
            enquiry.assigned_to_name ??
            (enquiry.assigned_to != null
              ? t("detail.rail.user_with_id", { id: enquiry.assigned_to })
              : t("detail.rail.unassigned"))
          }
        />
      </FactList>
      <EnquiryActions enquiry={enquiry} onOpen={onOpenDialog} />
    </div>
  );
}

// Collapsible rail panel. Children mount only while open, so the activity /
// notes queries inside them stay dormant until the operator expands the panel
// (no eager fetch of timelines the operator may never look at).
function RailPanel({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-border border-t pt-4">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="text-foreground flex w-full items-center justify-between text-sm font-semibold"
      >
        <span>{title}</span>
        {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
      </button>
      {open ? <div className="mt-2">{children}</div> : null}
    </div>
  );
}

// The quotes spine block: the existing quote-stack plus a disclosure that
// expands the inline builder. Defaults open only when there are no quotes yet
// — an enquiry that already has quotes opens compact (one click to add more).
function QuotesSection({ enquiry }: { enquiry: EnquiryDetail }) {
  const { t } = useTranslation("enquiries");
  const [building, setBuilding] = useState(enquiry.quotations.length === 0);
  const hasRole = useHasReservationsRole();

  const toggleLabel = building
    ? t("quotes_section.hide_builder")
    : enquiry.quotations.length > 0
      ? t("quotes_section.build_another_cta")
      : t("quotes_section.build_cta");

  return (
    <section className="space-y-3">
      <h2 className="text-foreground text-lg font-semibold">{t("quotes_section.heading")}</h2>
      <EnquiryQuoteStack quotations={enquiry.quotations} />
      {hasRole ? (
        <div className="space-y-4">
          <Button variant="outline" size="sm" onClick={() => setBuilding((v) => !v)}>
            {toggleLabel}
          </Button>
          {building ? (
            // Collapse back to the stack once a quote is committed — the new
            // quote appears in the list above via the enquiry-detail refetch.
            <QuoteBuilder enquiry={enquiry} onComplete={() => setBuilding(false)} />
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export function EnquiryDetailLayout() {
  const { t } = useTranslation("enquiries");
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
          title={is404 ? t("detail.not_found_title") : t("detail.load_failed_title")}
          description={is404 ? t("detail.not_found_body") : t("detail.load_failed_body")}
          onRetry={is404 ? undefined : () => query.refetch()}
        />
      </div>
    );
  }

  const enquiry = query.data;

  const handleReopen = async () => {
    try {
      await reopenMutation.mutateAsync("");
      toast.success(t("detail.reopen_confirm.success_message"));
      setDialog(null);
    } catch (error) {
      const message =
        error instanceof ApiError ? error.detail : t("detail.reopen_confirm.error_message");
      toast.error(message);
    }
  };

  return (
    <div>
      <PageHeader
        title={enquiry.reference}
        subtitle={guestName(enquiry)}
        breadcrumbs={[
          { label: t("detail.breadcrumb_list"), to: "/enquiries" },
          { label: enquiry.reference },
        ]}
      />

      <TwoColumn
        rightRail={
          <div className="space-y-4">
            <RailSummary enquiry={enquiry} onOpenDialog={setDialog} />
            <RailPanel title={t("tabs.activity")}>
              <ActivityTab enquiryId={enquiry.id} />
            </RailPanel>
            <RailPanel title={t("tabs.notes")}>
              <NotesTab enquiryId={enquiry.id} />
            </RailPanel>
          </div>
        }
      >
        <div className="space-y-10">
          <QuotesSection enquiry={enquiry} />
          <DetailsTab enquiry={enquiry} />
        </div>
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
        title={t("detail.reopen_confirm.title")}
        description={t("detail.reopen_confirm.description")}
        confirmLabel={t("detail.reopen_confirm.confirm_label")}
        busy={reopenMutation.isPending}
      />
    </div>
  );
}
