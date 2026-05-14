import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/lib/api/errors";
import type { EnquiryId } from "@/lib/query/keys";
import { useUsers } from "@/features/users/hooks";
import { userDisplayName, type UserSummary } from "@/features/users/schemas";
import { useAssignEnquiry } from "../hooks";

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
  // splits comma-separated values into repeated query params.
  const usersQuery = useUsers({
    role: "reservations,admin",
    is_active: true,
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

  // Make sure the currently-assigned user shows up even when they aren't in
  // the filtered/searched result set — otherwise the Select would briefly
  // display an empty value while editing.
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
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("assign.placeholders.search")}
              autoFocus
            />
            <Select value={selected} onValueChange={setSelected}>
              <SelectTrigger aria-label={t("assign.fields.operator")}>
                <SelectValue placeholder={t("assign.placeholders.select")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={UNASSIGNED_VALUE}>{t("assign.options.unassigned")}</SelectItem>
                {visibleUsers.map((u) => (
                  <SelectItem key={u.id} value={String(u.id)}>
                    {userDisplayName(u) || `#${u.id}`}
                    {u.email && userDisplayName(u) !== u.email ? (
                      <span className="text-muted-foreground ml-2 text-xs">{u.email}</span>
                    ) : null}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {isLoading ? (
              <p className="text-muted-foreground text-xs">{t("common:states.loading")}</p>
            ) : null}
            {hasError ? (
              <p className="text-destructive text-xs">{t("assign.errors.load_failed")}</p>
            ) : null}
            {!isLoading && !hasError && users.length === 0 ? (
              <p className="text-muted-foreground text-xs">{t("assign.empty")}</p>
            ) : null}
          </div>
          {topLevelError ? (
            <div
              className="bg-destructive/10 text-destructive border-destructive/40 rounded-md border p-3 text-sm"
              role="alert"
            >
              {topLevelError}
            </div>
          ) : null}
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
