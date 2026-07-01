import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { CheckboxLabel } from "@/components/ui/checkbox-label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import type { ContactId } from "@/lib/query/keys";
import { useSetContactTags } from "../hooks";
import { PERSON_TAGS } from "../personTags";
import { TagChips } from "./TagChips";

interface InlineTagEditorProps {
  contactId: ContactId;
  /** The persisted set, fed from the contact-detail cache the mutation updates. */
  tags: string[];
}

/**
 * GAP-053 #2: client-scoped tag editing inline, with no dialog — mirrors the
 * enquiry `LeadStatusCell` (Popover + per-edit audited mutation). Each checkbox
 * toggle PATCHes the whole `tags` set (the backend replaces it wholesale) and
 * optimistically updates the contact-detail cache, so selection state is driven
 * by the `tags` prop rather than a local copy that could fight a refetch. A
 * failure rolls the cache back and toasts. Per the role-gating convention the
 * edit affordance stays visible but disabled (with a tooltip) for users without
 * the reservations role. Gate the mount on clients-membership at the call site
 * (see `isClientContact`).
 */
export function InlineTagEditor({ contactId, tags }: InlineTagEditorProps) {
  const { t } = useTranslation("contacts");
  const canWrite = useHasReservationsRole();
  const [open, setOpen] = useState(false);
  const setTags = useSetContactTags(contactId);
  const submitting = setTags.isPending;

  const toggle = (value: string, checked: boolean) => {
    const next = checked ? [...tags, value] : tags.filter((v) => v !== value);
    setTags.mutate(next, {
      onError: () => toast.error(t("toasts.tags_update_failed")),
    });
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      {tags.length > 0 ? (
        <TagChips tags={tags} />
      ) : (
        <span className="text-muted-foreground text-sm">{t("empty.tags")}</span>
      )}
      {canWrite ? (
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <Button variant="outline" size="sm" aria-label={t("actions.edit_tags")}>
              {t("actions.edit_tags")}
            </Button>
          </PopoverTrigger>
          <PopoverContent align="start" className="w-56 p-2">
            <p className="text-muted-foreground px-1 pb-2 text-xs font-medium">
              {t("headings.edit_tags_dialog")}
            </p>
            <div className="space-y-1">
              {PERSON_TAGS.map((tag) => (
                <CheckboxLabel key={tag.value}>
                  <Checkbox
                    checked={tags.includes(tag.value)}
                    disabled={submitting}
                    onCheckedChange={(v) => toggle(tag.value, v === true)}
                  />
                  <span>{t(tag.labelKey)}</span>
                </CheckboxLabel>
              ))}
            </div>
          </PopoverContent>
        </Popover>
      ) : (
        <Tooltip>
          <TooltipTrigger asChild>
            <span>
              <Button variant="outline" size="sm" disabled aria-label={t("actions.edit_tags")}>
                {t("actions.edit_tags")}
              </Button>
            </span>
          </TooltipTrigger>
          <TooltipContent>{t("common:tooltips.reservations_role_required")}</TooltipContent>
        </Tooltip>
      )}
    </div>
  );
}
