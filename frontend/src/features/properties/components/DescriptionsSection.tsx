import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Section } from "@/components/data/Section";
import { ErrorState } from "@/components/feedback/ErrorState";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { ApiError } from "@/lib/api/errors";
import {
  useDeletePropertyDescription,
  usePropertyDescriptions,
  useUpsertPropertyDescription,
} from "../hooks";
import {
  DESCRIPTION_SECTIONS,
  INTERNAL_SECTION,
  WEBSITE_SECTIONS,
  isKnownSection,
  type DescriptionSection,
  type PropertyDescription,
} from "../schemas";

interface DescriptionsSectionProps {
  propertyId: number;
}

function bodiesFor(records: PropertyDescription[]): Record<DescriptionSection, string> {
  const map = Object.fromEntries(DESCRIPTION_SECTIONS.map((s) => [s, ""])) as Record<
    DescriptionSection,
    string
  >;
  for (const r of records) {
    // A section this build doesn't know (newer backend) is skipped rather than
    // rendered — see the schema note on `section`.
    if (isKnownSection(r.section)) {
      map[r.section] = r.body ?? "";
    }
  }
  return map;
}

export function DescriptionsSection({ propertyId }: DescriptionsSectionProps) {
  const { t } = useTranslation("properties");
  const canWrite = useHasReservationsRole();
  const descriptions = usePropertyDescriptions(propertyId);
  const upsertMutation = useUpsertPropertyDescription(propertyId);
  const deleteMutation = useDeletePropertyDescription(propertyId);

  const initialBodies = useMemo(
    () => bodiesFor(descriptions.data?.results ?? []),
    [descriptions.data?.results],
  );
  const [bodies, setBodies] = useState<Record<DescriptionSection, string>>(initialBodies);
  const [section, setSection] = useState<DescriptionSection>("overview");
  const [clearing, setClearing] = useState<DescriptionSection | null>(null);

  // Seed local bodies from the first successful fetch only — subsequent
  // refetches (e.g. after Save) must not clobber unsaved edits on other tabs.
  const seeded = useRef(false);
  useEffect(() => {
    if (!seeded.current && descriptions.data) {
      setBodies(initialBodies);
      seeded.current = true;
    }
  }, [descriptions.data, initialBodies]);

  const handleSave = async (target: DescriptionSection) => {
    try {
      await upsertMutation.mutateAsync({ section: target, body: bodies[target] });
      toast.success(t("descriptions.toasts.saved"));
    } catch (error) {
      if (error instanceof ApiError) {
        toast.error(error.detail);
      } else {
        toast.error(t("descriptions.toasts.save_failed"));
      }
    }
  };

  const handleClear = async () => {
    if (!clearing) return;
    try {
      await deleteMutation.mutateAsync({ section: clearing });
      // The `seeded` guard blocks the refetch from reseeding, so drop the local
      // copy explicitly — otherwise the cleared text stays on screen and Save
      // flips back to enabled, one click from re-creating what was just deleted.
      setBodies((prev) => ({ ...prev, [clearing]: "" }));
      toast.success(t("descriptions.toasts.cleared"));
      setClearing(null);
    } catch {
      toast.error(t("descriptions.toasts.clear_failed"));
    }
  };

  if (descriptions.isLoading) {
    return <Skeleton className="h-32 w-full" />;
  }

  if (descriptions.isError) {
    return (
      <ErrorState
        title={t("descriptions.errors.load_title")}
        description={t("descriptions.errors.load_body")}
        onRetry={() => descriptions.refetch()}
      />
    );
  }

  const savingSection = upsertMutation.isPending ? upsertMutation.variables?.section : undefined;

  // `label` disambiguates the internal-notes buttons from the six identically
  // captioned website ones; it tracks the pending state so it never contradicts
  // the visible text (aria-label wins for the accessible name). Website buttons
  // pass `undefined` — their visible caption already names them.
  const renderSaveButton = (s: DescriptionSection, label?: string) => {
    const saving = savingSection === s;
    const caption = saving ? t("descriptions.actions.saving") : t("descriptions.actions.save");
    return canWrite ? (
      <Button
        size="sm"
        aria-label={label && saving ? t("descriptions.actions.saving_internal") : label}
        onClick={() => handleSave(s)}
        // Gated per section, not on `isPending`: the mutation hook is shared, so
        // an in-flight internal-notes save would otherwise dead the Save button
        // under someone mid-edit on a website section.
        disabled={bodies[s] === initialBodies[s] || saving}
      >
        {caption}
      </Button>
    ) : (
      <Tooltip>
        <TooltipTrigger asChild>
          <span>
            <Button size="sm" aria-label={label} disabled>
              {t("descriptions.actions.save")}
            </Button>
          </span>
        </TooltipTrigger>
        <TooltipContent>{t("descriptions.save_disabled_tooltip")}</TooltipContent>
      </Tooltip>
    );
  };

  const renderClearButton = (s: DescriptionSection, label?: string) =>
    canWrite ? (
      <Button
        variant="outline"
        size="sm"
        aria-label={label}
        onClick={() => setClearing(s)}
        disabled={!initialBodies[s]}
      >
        {t("descriptions.actions.clear")}
      </Button>
    ) : null;

  return (
    <div className="space-y-6">
      <Section title={t("descriptions.groups.website")}>
        <Tabs value={section} onValueChange={(v) => setSection(v as DescriptionSection)}>
          {/* Six triggers with full-length labels overflow a narrow viewport;
              `TabsList` is `w-fit` and the triggers are `whitespace-nowrap`, so
              without this they clip rather than wrap. */}
          <div className="overflow-x-auto">
            <TabsList>
              {WEBSITE_SECTIONS.map((s) => (
                <TabsTrigger key={s} value={s}>
                  {t(`descriptions.sections.${s}`)}
                </TabsTrigger>
              ))}
            </TabsList>
          </div>
          {WEBSITE_SECTIONS.map((s) => (
            <TabsContent key={s} value={s} className="space-y-3">
              <Label htmlFor={`description-${s}`} className="sr-only">
                {t(`descriptions.sections.${s}`)}
              </Label>
              <Textarea
                id={`description-${s}`}
                rows={10}
                value={bodies[s]}
                disabled={!canWrite}
                onChange={(e) => setBodies((prev) => ({ ...prev, [s]: e.target.value }))}
                placeholder={t("descriptions.body_placeholder")}
              />
              <div className="flex items-center justify-end gap-2">
                {renderClearButton(s)}
                {renderSaveButton(s)}
              </div>
            </TabsContent>
          ))}
        </Tabs>
      </Section>

      <Section
        title={t("descriptions.groups.internal")}
        actions={<Badge variant="outline">{t("descriptions.groups.internal_badge")}</Badge>}
      >
        <div className="space-y-3">
          <Label htmlFor={`description-${INTERNAL_SECTION}`} className="sr-only">
            {t(`descriptions.sections.${INTERNAL_SECTION}`)}
          </Label>
          <Textarea
            id={`description-${INTERNAL_SECTION}`}
            rows={6}
            value={bodies[INTERNAL_SECTION]}
            disabled={!canWrite}
            onChange={(e) => setBodies((prev) => ({ ...prev, [INTERNAL_SECTION]: e.target.value }))}
            placeholder={t("descriptions.internal_placeholder")}
          />
          <div className="flex items-center justify-end gap-2">
            {renderClearButton(INTERNAL_SECTION, t("descriptions.actions.clear_internal"))}
            {renderSaveButton(INTERNAL_SECTION, t("descriptions.actions.save_internal"))}
          </div>
        </div>
      </Section>

      {clearing ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setClearing(null)}
          onConfirm={handleClear}
          title={t("descriptions.clear_confirm.title")}
          description={t("descriptions.clear_confirm.description")}
          confirmLabel={t("descriptions.clear_confirm.confirm")}
          destructive
          busy={deleteMutation.isPending}
        />
      ) : null}
    </div>
  );
}
