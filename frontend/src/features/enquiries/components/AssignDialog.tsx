import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { CheckIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/cn";
import { ApiError } from "@/lib/api/errors";
import type { EnquiryId } from "@/lib/query/keys";
import { useUsers } from "@/features/users/hooks";
import { userDisplayName, type UserSummary } from "@/features/users/schemas";
import { useAssignEnquiry } from "../hooks";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";

interface AssignDialogProps {
  enquiryId: EnquiryId;
  currentUserId: number | null | undefined;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const UNASSIGNED_VALUE = "__unassigned__";

export function AssignDialog({ enquiryId, currentUserId, open, onOpenChange }: AssignDialogProps) {
  const { t } = useTranslation("enquiries");
  const mutation = useAssignEnquiry(enquiryId);
  const [selected, setSelected] = useState<string>(
    currentUserId != null ? String(currentUserId) : UNASSIGNED_VALUE,
  );
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setSelected(currentUserId != null ? String(currentUserId) : UNASSIGNED_VALUE);
      setSearch("");
      setDebouncedSearch("");
      setTopLevelError(null);
    }
  }, [open, currentUserId]);

  useEffect(() => {
    if (search === debouncedSearch) return;
    const handle = setTimeout(() => setDebouncedSearch(search), 250);
    return () => clearTimeout(handle);
  }, [search, debouncedSearch]);

  // Mirror the legacy product filter — operators handling enquiries have the
  // reservations or admin role. Backend filter is `role=` exact, but our api.ts
  // splits comma-separated values into repeated query params. `is_staff: true`
  // keeps non-staff owner-portal users out of the picker (the backend rejects
  // them anyway, but don't offer what will 400).
  const usersQuery = useUsers({
    role: "reservations,admin",
    is_active: true,
    is_staff: true,
    search: debouncedSearch || undefined,
  });

  const handleSubmit = async () => {
    setTopLevelError(null);
    const userId = selected === UNASSIGNED_VALUE ? null : Number(selected);
    try {
      await mutation.mutateAsync({ user: userId });
      toast.success(userId == null ? t("assign.toasts.unassigned") : t("assign.toasts.assigned"));
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        setTopLevelError(error.detail);
      } else {
        toast.error(t("common:errors.generic"));
      }
    }
  };

  const users = usersQuery.data?.results ?? [];
  const hasError = usersQuery.isError;
  const isLoading = usersQuery.isLoading;
  const hasSearch = debouncedSearch.trim().length > 0;

  // Make sure the currently-assigned user shows up even when they aren't in
  // the filtered/searched result set — otherwise the row vanishes mid-edit.
  const visibleUsers: UserSummary[] = (() => {
    if (currentUserId == null) return users;
    if (users.some((u) => u.id === currentUserId)) return users;
    const placeholder: UserSummary = {
      id: currentUserId,
      email: "",
      first_name: "",
      last_name: "",
      role: null,
      is_active: true,
    };
    return [placeholder, ...users];
  })();

  const showEmptyForSearch = !isLoading && !hasError && hasSearch && visibleUsers.length === 0;
  const showEmptyNoOperators = !isLoading && !hasError && !hasSearch && visibleUsers.length === 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("assign.title")}</DialogTitle>
          <DialogDescription>{t("assign.description")}</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-2">
            <Label htmlFor="assign-operator-search">{t("assign.fields.operator")}</Label>
            <Input
              id="assign-operator-search"
              type="text"
              role="combobox"
              aria-expanded="true"
              aria-controls="assign-operator-list"
              aria-autocomplete="list"
              autoComplete="off"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("assign.placeholders.search")}
              autoFocus
            />
            <div
              id="assign-operator-list"
              role="listbox"
              aria-label={t("assign.fields.operator")}
              className="bg-popover max-h-64 overflow-y-auto rounded-md border"
            >
              <OperatorOption
                value={UNASSIGNED_VALUE}
                label={t("assign.options.unassigned")}
                selected={selected === UNASSIGNED_VALUE}
                onSelect={setSelected}
              />
              {visibleUsers.map((u) => {
                const value = String(u.id);
                const displayName = userDisplayName(u) || `#${u.id}`;
                return (
                  <OperatorOption
                    key={u.id}
                    value={value}
                    label={displayName}
                    sublabel={u.email && displayName !== u.email ? u.email : undefined}
                    selected={selected === value}
                    onSelect={setSelected}
                  />
                );
              })}
              {showEmptyForSearch ? (
                <p className="text-muted-foreground px-3 py-4 text-center text-xs">
                  {t("assign.empty")}
                </p>
              ) : null}
            </div>
            {isLoading ? (
              <p className="text-muted-foreground text-xs">{t("common:states.loading")}</p>
            ) : null}
            {hasError ? (
              <p className="text-destructive text-xs">{t("assign.errors.load_failed")}</p>
            ) : null}
            {showEmptyNoOperators ? (
              <p className="text-muted-foreground text-xs">{t("assign.no_operators")}</p>
            ) : null}
          </div>
          <FormErrorAlert message={topLevelError} />
        </div>
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={mutation.isPending}
          >
            {t("common:actions.cancel")}
          </Button>
          <Button type="button" onClick={handleSubmit} disabled={mutation.isPending}>
            {mutation.isPending ? t("common:actions.saving") : t("assign.actions.submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface OperatorOptionProps {
  value: string;
  label: string;
  sublabel?: string;
  selected: boolean;
  onSelect: (value: string) => void;
}

function OperatorOption({ value, label, sublabel, selected, onSelect }: OperatorOptionProps) {
  return (
    <button
      type="button"
      role="option"
      aria-selected={selected}
      onClick={() => onSelect(value)}
      className={cn(
        "hover:bg-accent focus-visible:bg-accent flex w-full items-center gap-2 px-3 py-2 text-left text-sm outline-none",
        selected && "bg-accent/60",
      )}
    >
      <CheckIcon
        className={cn("size-4 shrink-0", selected ? "opacity-100" : "opacity-0")}
        aria-hidden
      />
      <span className="min-w-0 flex-1 truncate">
        {label}
        {sublabel ? <span className="text-muted-foreground ml-2 text-xs">{sublabel}</span> : null}
      </span>
    </button>
  );
}
