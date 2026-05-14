import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
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
  type DescriptionSection,
  type PropertyDescription,
} from "../schemas";

interface DescriptionsSectionProps {
  propertyId: number;
}

function bodiesFor(records: PropertyDescription[]): Record<DescriptionSection, string> {
  const map: Record<DescriptionSection, string> = {
    overview: "",
    house_rules: "",
    villa_info: "",
    further_info: "",
  };
  for (const r of records) {
    map[r.section] = r.body ?? "";
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

  const isDirty = bodies[section] !== initialBodies[section];

  const handleSave = async () => {
    try {
      await upsertMutation.mutateAsync({ section, body: bodies[section] });
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

  const saveButton = canWrite ? (
    <Button size="sm" onClick={handleSave} disabled={!isDirty || upsertMutation.isPending}>
      {upsertMutation.isPending ? t("descriptions.actions.saving") : t("descriptions.actions.save")}
    </Button>
  ) : (
    <Tooltip>
      <TooltipTrigger asChild>
        <span>
          <Button size="sm" disabled>
            {t("descriptions.actions.save")}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>{t("descriptions.save_disabled_tooltip")}</TooltipContent>
    </Tooltip>
  );

  return (
    <div className="space-y-4">
      <Tabs value={section} onValueChange={(v) => setSection(v as DescriptionSection)}>
        <TabsList>
          {DESCRIPTION_SECTIONS.map((s) => (
            <TabsTrigger key={s} value={s}>
              {t(`descriptions.sections.${s}`)}
            </TabsTrigger>
          ))}
        </TabsList>
        {DESCRIPTION_SECTIONS.map((s) => (
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
              {canWrite ? (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setClearing(s)}
                  disabled={!initialBodies[s]}
                >
                  {t("descriptions.actions.clear")}
                </Button>
              ) : null}
              {saveButton}
            </div>
          </TabsContent>
        ))}
      </Tabs>

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
