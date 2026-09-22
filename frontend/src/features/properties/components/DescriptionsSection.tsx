import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
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
  isKnownSection,
  type DescriptionSection,
  type PropertyDescription,
} from "../schemas";

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
  /**
   * The tab's video URL editor, rendered between the website copy and the
   * internal notes. Passed in rather than owned here: the video URL is a
   * property field with its own form, and it must stay on screen while the
   * descriptions load or fail (the guard dialog still needs a visible prompt
   * for a dirty video URL after a descriptions 500).
   */
  videoSection?: ReactNode;
}

type CopySection = Exclude<DescriptionSection, typeof INTERNAL_SECTION>;

/** The website copy, top to bottom as the public site shows it. */
const COPY_SECTIONS = DESCRIPTION_SECTIONS.filter((s): s is CopySection => s !== INTERNAL_SECTION);

/**
 * How each website section is edited: a subtitle (the public site renders it
 * as a heading — `web_des_1` is the top one) gets a few rows, a paragraph
 * gets more; `hinted` sections carry a `descriptions.hints.*` note beside
 * the label saying where the copy shows. Typed as a Record so a section
 * added to `DESCRIPTION_SECTIONS` cannot render without an entry here.
 */
const EDITORS: Record<CopySection, { rows: number; hinted: boolean }> = {
  web_des_1: { rows: 3, hinted: true },
  web_des_2: { rows: 8, hinted: true },
  interior_sub: { rows: 3, hinted: false },
  interior_para: { rows: 8, hinted: false },
  exterior_sub: { rows: 3, hinted: false },
  exterior_para: { rows: 8, hinted: false },
  location_sub: { rows: 3, hinted: false },
  location_para: { rows: 8, hinted: false },
  rooms: { rows: 8, hinted: true },
  house_rules: { rows: 8, hinted: true },
};

function bodiesFor(records: PropertyDescription[]): Record<DescriptionSection, string> {
  const map = Object.fromEntries(DESCRIPTION_SECTIONS.map((s) => [s, ""])) as Record<
    DescriptionSection,
    string
  >;
  for (const r of records) {
    // A section this build doesn't know (newer backend, or a retired one an
    // older cache still echoes) is skipped rather than rendered — see the
    // schema note on `section`.
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
  videoSection,
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
  const [clearing, setClearing] = useState<DescriptionSection | null>(null);
  // Per-section, not `upsertMutation.variables`: that holds only the most
  // recent call, so saving one section while another is still in flight
  // dropped the first one's "Saving…" caption and re-enabled its button.
  const [inFlight, setInFlight] = useState<ReadonlySet<DescriptionSection>>(new Set());

  // Seed local bodies from the first successful fetch only — subsequent
  // refetches (e.g. after Save) must not clobber unsaved edits elsewhere.
  const seeded = useRef(false);
  useEffect(() => {
    if (!seeded.current && descriptions.data) {
      setBodies(initialBodies);
      seeded.current = true;
    }
  }, [descriptions.data, initialBodies]);

  // The tab's Reset: drop every draft. State adjusted during render rather
  // than by remounting, so scroll position and focus survive.
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

  // Every button carries its section in the accessible name: eleven editors
  // stack in one column and every caption reads "Save" / "Clear", so the
  // visible text alone names none of them — and Clear is a hard DELETE with
  // nothing to undo it. The name is the short label, never the hint.
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

  // One editor per section: label (plus hint), textarea and Clear/Save row —
  // each section is its own API row. The hint sits beside the <label>, not
  // inside it, so the textbox's accessible name stays the short section name
  // that the Save/Clear labels and the Clear dialog use; `aria-describedby`
  // still reads it out.
  const renderEditor = (s: CopySection) => {
    const { rows, hinted } = EDITORS[s];
    const hintId = `description-${s}-hint`;
    return (
      <div key={s} className="space-y-3">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <Label htmlFor={`description-${s}`}>{t(`descriptions.sections.${s}`)}</Label>
          {hinted ? (
            <span id={hintId} className="text-muted-foreground text-sm">
              {t(`descriptions.hints.${s}`)}
            </span>
          ) : null}
        </div>
        <Textarea
          id={`description-${s}`}
          rows={rows}
          value={bodies[s]}
          disabled={!canWrite}
          aria-describedby={hinted ? hintId : undefined}
          onChange={(e) => setBodies((prev) => ({ ...prev, [s]: e.target.value }))}
          placeholder={t("descriptions.body_placeholder")}
        />
        <div className="flex items-center justify-end gap-2">
          {renderClearButton(s)}
          {renderSaveButton(s)}
        </div>
      </div>
    );
  };

  // A single render, not early returns: the video section must show in every
  // branch. Internal notes wait for the fetch — with unseeded bodies a Save
  // there would overwrite notes that never loaded.
  const loaded = !descriptions.isLoading && !descriptions.isError;

  return (
    <div className="space-y-6">
      {descriptions.isLoading ? (
        // One placeholder per editor, sized like it: the video section below
        // must not leap down the page when the copy lands.
        <Section title={t("descriptions.groups.copy")}>
          <div className="space-y-6">
            {COPY_SECTIONS.map((s) => (
              <Skeleton key={s} className={EDITORS[s].rows > 3 ? "h-56 w-full" : "h-32 w-full"} />
            ))}
          </div>
        </Section>
      ) : descriptions.isError ? (
        <ErrorState
          title={t("descriptions.errors.load_title")}
          description={t("descriptions.errors.load_body")}
          onRetry={() => descriptions.refetch()}
        />
      ) : (
        // One column in website order, so a reviewer reads the villa's copy
        // top to bottom as a guest would, instead of clicking through tabs.
        <Section title={t("descriptions.groups.copy")}>
          <div className="space-y-6">{COPY_SECTIONS.map(renderEditor)}</div>
        </Section>
      )}

      {videoSection}

      {loaded ? (
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
              onChange={(e) =>
                setBodies((prev) => ({ ...prev, [INTERNAL_SECTION]: e.target.value }))
              }
              placeholder={t("descriptions.internal_placeholder")}
            />
            <div className="flex items-center justify-end gap-2">
              {renderClearButton(INTERNAL_SECTION)}
              {renderSaveButton(INTERNAL_SECTION)}
            </div>
          </div>
        </Section>
      ) : null}

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
