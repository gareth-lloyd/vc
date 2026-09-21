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
  DESCRIPTION_BLOCKS,
  DESCRIPTION_SECTIONS,
  INTERNAL_SECTION,
  SINGLE_SECTIONS,
  isKnownSection,
  type DescriptionBlock,
  type DescriptionSection,
  type PropertyDescription,
} from "../schemas";

/** Tab ids: one per sub/para block, then one per unpaired section. */
type TabId = DescriptionBlock["key"] | (typeof SINGLE_SECTIONS)[number];

interface DescriptionsSectionProps {
  propertyId: number;
  /**
   * Reports whether any section holds typed-but-unsaved text, so the tab can
   * fold it into its single unsaved-changes guard (GAP-083 — one guard per
   * route; never add a second one in here).
   */
  onDirtyChange?: (dirty: boolean) => void;
  /** Bump to discard every draft and re-seed from the cached server text. */
  resetVersion?: number;
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

export function DescriptionsSection({
  propertyId,
  onDirtyChange,
  resetVersion = 0,
}: DescriptionsSectionProps) {
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
  const [tab, setTab] = useState<TabId>("web");
  const [clearing, setClearing] = useState<DescriptionSection | null>(null);
  // Per-section, not `upsertMutation.variables`: that holds only the most
  // recent call, so saving a block's para while its sub is still in flight
  // dropped the sub's "Saving…" caption and re-enabled its button.
  const [inFlight, setInFlight] = useState<ReadonlySet<DescriptionSection>>(new Set());

  // Seed local bodies from the first successful fetch only — subsequent
  // refetches (e.g. after Save) must not clobber unsaved edits on other tabs.
  const seeded = useRef(false);
  useEffect(() => {
    if (!seeded.current && descriptions.data) {
      setBodies(initialBodies);
      seeded.current = true;
    }
  }, [descriptions.data, initialBodies]);

  // The tab's Reset: drop every draft. State adjusted during render rather
  // than by remounting, so the operator stays on the block they were editing.
  const [seenReset, setSeenReset] = useState(resetVersion);
  if (seenReset !== resetVersion) {
    setSeenReset(resetVersion);
    // A section mid-save keeps its body: `initialBodies` still holds the
    // pre-save text, and restoring that would read as a fresh draft — one
    // click from overwriting the copy that just persisted.
    setBodies((prev) => {
      const next = { ...initialBodies };
      for (const s of inFlight) next[s] = prev[s];
      return next;
    });
  }

  // Dirty = differs from the last server echo. Gated on `seeded` so the render
  // that carries the first fetch (bodies still "") is not reported as dirty.
  // A section whose own save or clear is in flight is not counted — the
  // mutation stays pending until the refetch echoes the new body, and the
  // guard must neither block a navigation for already-persisted text nor
  // swallow the click when the echo lands. Only that section: a draft
  // elsewhere stays guarded throughout.
  const reportedDirty =
    seeded.current &&
    DESCRIPTION_SECTIONS.some(
      (s) =>
        !inFlight.has(s) &&
        !(deleteMutation.isPending && s === clearing) &&
        bodies[s] !== initialBodies[s],
    );
  useEffect(() => {
    onDirtyChange?.(reportedDirty);
    return () => onDirtyChange?.(false);
  }, [reportedDirty, onDirtyChange]);

  const handleSave = async (target: DescriptionSection) => {
    setInFlight((prev) => new Set(prev).add(target));
    try {
      await upsertMutation.mutateAsync({ section: target, body: bodies[target] });
      toast.success(t("descriptions.toasts.saved"));
    } catch (error) {
      if (error instanceof ApiError) {
        toast.error(error.detail);
      } else {
        toast.error(t("descriptions.toasts.save_failed"));
      }
    } finally {
      setInFlight((prev) => {
        const next = new Set(prev);
        next.delete(target);
        return next;
      });
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

  // Every button carries its section in the accessible name. Two editors now
  // share one panel (a block's sub and para) and both captions read "Save" /
  // "Clear", so the visible text alone names neither — and Clear is a hard
  // DELETE with nothing to undo it.
  const renderSaveButton = (s: DescriptionSection) => {
    const section = t(`descriptions.sections.${s}`);
    const saving = inFlight.has(s);
    const caption = saving ? t("descriptions.actions.saving") : t("descriptions.actions.save");
    return canWrite ? (
      <Button
        size="sm"
        aria-label={
          saving
            ? t("descriptions.actions.saving_named", { section })
            : t("descriptions.actions.save_named", { section })
        }
        onClick={() => handleSave(s)}
        // Gated per section, not on the shared mutation's `isPending`: an
        // in-flight save would otherwise dead every other Save button on the
        // page, including the one under someone mid-edit.
        disabled={bodies[s] === initialBodies[s] || saving}
      >
        {caption}
      </Button>
    ) : (
      <Tooltip>
        <TooltipTrigger asChild>
          <span>
            <Button
              size="sm"
              aria-label={t("descriptions.actions.save_named", { section })}
              disabled
            >
              {t("descriptions.actions.save")}
            </Button>
          </span>
        </TooltipTrigger>
        <TooltipContent>{t("descriptions.save_disabled_tooltip")}</TooltipContent>
      </Tooltip>
    );
  };

  const renderClearButton = (s: DescriptionSection) =>
    canWrite ? (
      <Button
        variant="outline"
        size="sm"
        aria-label={t("descriptions.actions.clear_named", {
          section: t(`descriptions.sections.${s}`),
        })}
        onClick={() => setClearing(s)}
        disabled={!initialBodies[s]}
      >
        {t("descriptions.actions.clear")}
      </Button>
    ) : null;

  // One block column: its own label, textarea and Clear/Save row, because
  // each section is its own API row even though the pair renders together.
  const renderEditor = (s: DescriptionSection, rows: number) => (
    <div className="space-y-3">
      <Label htmlFor={`description-${s}`}>{t(`descriptions.sections.${s}`)}</Label>
      <Textarea
        id={`description-${s}`}
        rows={rows}
        value={bodies[s]}
        disabled={!canWrite}
        onChange={(e) => setBodies((prev) => ({ ...prev, [s]: e.target.value }))}
        placeholder={t("descriptions.body_placeholder")}
      />
      <div className="flex items-center justify-end gap-2">
        {renderClearButton(s)}
        {renderSaveButton(s)}
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      <Section title={t("descriptions.groups.copy")}>
        <Tabs value={tab} onValueChange={(v) => setTab(v as TabId)}>
          {/* Seven triggers with full-length labels overflow a narrow viewport;
              `TabsList` is `w-fit` and the triggers are `whitespace-nowrap`, so
              without this they clip rather than wrap. */}
          <div className="overflow-x-auto">
            <TabsList>
              {DESCRIPTION_BLOCKS.map((b) => (
                <TabsTrigger key={b.key} value={b.key}>
                  {t(`descriptions.blocks.${b.key}`)}
                </TabsTrigger>
              ))}
              {SINGLE_SECTIONS.map((s) => (
                <TabsTrigger key={s} value={s}>
                  {t(`descriptions.sections.${s}`)}
                </TabsTrigger>
              ))}
            </TabsList>
          </div>
          {DESCRIPTION_BLOCKS.map((b) => (
            // Sub left, para right — the legacy edit screen's two columns.
            <TabsContent key={b.key} value={b.key} className="grid gap-6 md:grid-cols-2">
              {renderEditor(b.sub, 4)}
              {renderEditor(b.para, 10)}
            </TabsContent>
          ))}
          {SINGLE_SECTIONS.map((s) => (
            <TabsContent key={s} value={s} className="space-y-3">
              {/* House rules is the one section here that is never published:
                  it is snapshotted onto the booking contract (GAP-094), and
                  five backend leak guards keep it out of every public
                  payload. Say so where it is edited. */}
              {s === "house_rules" ? (
                <p className="text-muted-foreground text-sm">
                  {t("descriptions.house_rules_hint")}
                </p>
              ) : null}
              {renderEditor(s, 10)}
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
            {renderClearButton(INTERNAL_SECTION)}
            {renderSaveButton(INTERNAL_SECTION)}
          </div>
        </div>
      </Section>

      {clearing ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setClearing(null)}
          onConfirm={handleClear}
          title={t("descriptions.clear_confirm.title", {
            section: t(`descriptions.sections.${clearing}`),
          })}
          description={t("descriptions.clear_confirm.description")}
          confirmLabel={t("descriptions.clear_confirm.confirm")}
          destructive
          busy={deleteMutation.isPending}
        />
      ) : null}
    </div>
  );
}
