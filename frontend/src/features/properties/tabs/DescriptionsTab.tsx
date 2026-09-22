import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Section } from "@/components/data/Section";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { ApiError } from "@/lib/api/errors";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { useUnsavedChangesGuard } from "@/lib/useUnsavedChangesGuard";
import { useUpdateProperty } from "../hooks";
import {
  propertyVideoFormSchema,
  type PropertyDetail,
  type PropertyVideoFormInput,
} from "../schemas";
import { DescriptionsSection } from "../components/DescriptionsSection";

interface DescriptionsContext {
  property: PropertyDetail;
}

/**
 * The villa's copy on its own tab (GAP-090), one column in website order: the
 * website sections, then the video URL, then the staff-only internal notes —
 * the nine-field legacy screen plus what we added since. Everything here
 * saves explicitly and separately, so the tab owns the route's single
 * unsaved-changes guard and the sections report their drafts up to it. The
 * video form stays here (it is a property field, not a description) and is
 * handed to the section as a node so it can render in its place.
 */
export function DescriptionsTab() {
  const { property } = useOutletContext<DescriptionsContext>();
  // Keyed on the property: the layout keeps the Outlet mounted across a
  // property → property navigation when the target is cached, and every draft
  // in here belongs to one villa — carried over, Save would write villa A's
  // copy onto villa B.
  return <DescriptionsTabBody key={property.id} property={property} />;
}

function DescriptionsTabBody({ property }: DescriptionsContext) {
  const { t } = useTranslation("properties");
  const canWrite = useHasReservationsRole();
  const videoMutation = useUpdateProperty(property.id);
  const [videoError, setVideoError] = useState<string | null>(null);

  const form = useForm<PropertyVideoFormInput>({
    resolver: zodResolver(propertyVideoFormSchema),
    defaultValues: { video_url: property.video_url ?? "" },
  });
  // A refetched `video_url` (changed in another session) reaches a pristine
  // form rather than being silently overwritten by the next save; a draft is
  // left alone. Property → property is handled by the key above.
  const serverVideoUrl = property.video_url ?? "";
  useEffect(() => {
    if (!form.formState.isDirty) form.reset({ video_url: serverVideoUrl });
  }, [serverVideoUrl, form]);

  // GAP-083: one guard per route (React Router allows a single blocker) —
  // compose here, never add a second guard inside a section. Neither half is
  // guarded while its own save is in flight (a failed save after the operator
  // has left is the same accepted trade-off as FeaturesTab's); the section
  // applies the rule per section before reporting.
  const [descriptionsDirty, setDescriptionsDirty] = useState(false);
  const [resetVersion, setResetVersion] = useState(0);
  // One flag for the badge, Reset and the guard, so they cannot disagree
  // mid-save (a Reset then would be undone by the save's own echo).
  const videoDirty = form.formState.isDirty && !videoMutation.isPending;
  const anyDirty = videoDirty || descriptionsDirty;
  const guard = useUnsavedChangesGuard(anyDirty);

  const handleVideoSave = form.handleSubmit(async (values) => {
    setVideoError(null);
    try {
      // `""` is sent as-is: that is how the column is cleared (GAP-024).
      await videoMutation.mutateAsync({ video_url: values.video_url });
      form.reset(values);
      toast.success(t("descriptions.video.toasts.saved"));
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        // The backend's URLField is the only URL validation there is.
        setVideoError(applyApiErrorToForm(form, error).detail);
      } else {
        toast.error(t("descriptions.video.toasts.save_failed"));
      }
    }
  });

  const handleReset = () => {
    form.reset({ video_url: serverVideoUrl });
    setVideoError(null);
    setResetVersion((v) => v + 1);
  };

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">{t("descriptions.title")}</h2>
        <div className="flex items-center gap-2">
          {anyDirty && (
            <Badge variant="outline" className="border-warning/40 bg-warning/10 text-warning">
              {t("common:unsaved.badge")}
            </Badge>
          )}
          <Button variant="outline" size="sm" onClick={handleReset} disabled={!anyDirty}>
            {t("descriptions.actions.reset")}
          </Button>
        </div>
      </div>

      {/* Rendered unconditionally (DialogContent is portalled): the section
          below swaps itself for a skeleton or ErrorState, and the guard must
          never hold a navigation without a visible prompt. */}
      {guard.blocked ? (
        <ConfirmDialog
          open
          onOpenChange={(open) => !open && guard.reset()}
          onConfirm={guard.proceed}
          title={t("common:unsaved.title")}
          description={t("common:unsaved.description")}
          confirmLabel={t("common:unsaved.discard")}
          cancelLabel={t("common:unsaved.stay")}
          destructive
        />
      ) : null}

      <DescriptionsSection
        propertyId={property.id}
        onDirtyChange={setDescriptionsDirty}
        resetVersion={resetVersion}
        videoSection={
          <Section title={t("descriptions.video.title")}>
            {/* `noValidate`: the browser's own type=url check would swallow the
                submit silently; the backend's message is the one we show. */}
            <form onSubmit={handleVideoSave} noValidate className="space-y-3">
              <div className="space-y-2">
                <Label htmlFor="prop-video-url">{t("descriptions.video.label")}</Label>
                <Input
                  id="prop-video-url"
                  type="url"
                  inputMode="url"
                  placeholder={t("descriptions.video.placeholder")}
                  // The column's own limit; the backend stays the URL authority.
                  maxLength={200}
                  disabled={!canWrite}
                  aria-invalid={Boolean(form.formState.errors.video_url)}
                  aria-describedby="prop-video-url-help"
                  {...form.register("video_url")}
                />
                <p id="prop-video-url-help" className="text-muted-foreground text-xs">
                  {t("descriptions.video.help")}
                </p>
              </div>
              <FormErrorAlert message={videoError} fieldErrors={form.formState.errors} />
              <div className="flex justify-end">
                {canWrite ? (
                  <Button type="submit" size="sm" disabled={!videoDirty}>
                    {videoMutation.isPending
                      ? t("descriptions.video.saving")
                      : t("descriptions.video.save")}
                  </Button>
                ) : (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span>
                        <Button type="button" size="sm" disabled>
                          {t("descriptions.video.save")}
                        </Button>
                      </span>
                    </TooltipTrigger>
                    <TooltipContent>{t("descriptions.save_disabled_tooltip")}</TooltipContent>
                  </Tooltip>
                )}
              </div>
            </form>
          </Section>
        }
      />
    </div>
  );
}
