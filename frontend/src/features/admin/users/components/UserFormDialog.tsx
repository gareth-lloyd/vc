import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { ApiError } from "@/lib/api/errors";
import { useCreateUser, useUpdateUser } from "@/features/users/hooks";
import {
  STAFF_ROLES,
  userCreateInputSchema,
  userUpdateInputSchema,
  type StaffRole,
  type UserCreateInput,
  type UserDetail,
  type UserSummary,
  type UserUpdateInput,
} from "@/features/users/schemas";

interface CommonProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface CreateProps extends CommonProps {
  mode: "create";
}

interface EditProps extends CommonProps {
  mode: "edit";
  user: UserSummary | UserDetail;
}

type UserFormDialogProps = CreateProps | EditProps;

const CREATE_DEFAULTS: UserCreateInput = {
  email: "",
  first_name: "",
  last_name: "",
  role: "viewer",
  password: "",
  is_active: true,
};

function editDefaults(user: UserSummary | UserDetail): UserUpdateInput {
  const rawRole = (user.role ?? "viewer").toLowerCase();
  const role = (STAFF_ROLES as string[]).includes(rawRole)
    ? (rawRole as StaffRole)
    : ("viewer" as StaffRole);
  return {
    email: user.email,
    first_name: user.first_name ?? "",
    last_name: user.last_name ?? "",
    role,
    is_active: user.is_active,
  };
}

export function UserFormDialog(props: UserFormDialogProps) {
  const { open, onOpenChange } = props;
  const isCreate = props.mode === "create";
  const { t } = useTranslation("admin");

  const form = useForm<UserCreateInput | UserUpdateInput>({
    resolver: zodResolver(isCreate ? userCreateInputSchema : userUpdateInputSchema),
    defaultValues: isCreate ? CREATE_DEFAULTS : editDefaults(props.user),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  const createMutation = useCreateUser();
  const updateMutation = useUpdateUser(isCreate ? 0 : props.user.id);
  const submitting = createMutation.isPending || updateMutation.isPending;

  useEffect(() => {
    if (open) {
      form.reset(isCreate ? CREATE_DEFAULTS : editDefaults(props.user));
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? null : props.user.id]);

  const roleValue = form.watch("role") as StaffRole | undefined;
  const isActiveValue = form.watch("is_active") as boolean | undefined;

  const handleSubmit = async (values: UserCreateInput | UserUpdateInput) => {
    setTopLevelError(null);
    try {
      if (isCreate) {
        await createMutation.mutateAsync(values as UserCreateInput);
        toast.success(t("users.toasts.created"));
      } else {
        await updateMutation.mutateAsync(values as UserUpdateInput);
        toast.success(t("users.toasts.updated"));
      }
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        setTopLevelError(detail);
      } else {
        toast.error(t("common:errors.generic"));
      }
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {isCreate ? t("users.dialog.create_title") : t("users.dialog.edit_title")}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="user-email">{t("users.dialog.fields.email")}</Label>
            <Input id="user-email" type="email" {...form.register("email")} />
            {form.formState.errors.email ? (
              <p className="text-destructive text-sm" role="alert">
                {form.formState.errors.email.message}
              </p>
            ) : null}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="user-first-name">{t("users.dialog.fields.first_name")}</Label>
              <Input id="user-first-name" {...form.register("first_name")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="user-last-name">{t("users.dialog.fields.last_name")}</Label>
              <Input id="user-last-name" {...form.register("last_name")} />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="user-role">{t("users.dialog.fields.role")}</Label>
            <Select
              value={roleValue ?? "viewer"}
              onValueChange={(v) => form.setValue("role", v as StaffRole)}
            >
              <SelectTrigger id="user-role" aria-label={t("users.dialog.fields.role")}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {STAFF_ROLES.map((r) => (
                  <SelectItem key={r} value={r}>
                    {t(`users.roles.${r}` as "users.roles.admin")}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {form.formState.errors.role ? (
              <p className="text-destructive text-sm" role="alert">
                {form.formState.errors.role.message}
              </p>
            ) : null}
          </div>

          {isCreate ? (
            <div className="space-y-2">
              <Label htmlFor="user-password">{t("users.dialog.fields.password")}</Label>
              <Input
                id="user-password"
                type="password"
                autoComplete="new-password"
                {...form.register("password")}
              />
              <p className="text-muted-foreground text-xs">
                {t("users.dialog.fields.password_hint")}
              </p>
              {"password" in form.formState.errors && form.formState.errors.password ? (
                <p className="text-destructive text-sm" role="alert">
                  {(form.formState.errors.password as { message?: string }).message}
                </p>
              ) : null}
            </div>
          ) : null}

          <div className="flex items-center gap-2">
            <Checkbox
              id="user-is-active"
              checked={isActiveValue ?? true}
              onCheckedChange={(checked) => form.setValue("is_active", Boolean(checked))}
            />
            <Label htmlFor="user-is-active">{t("users.dialog.fields.is_active")}</Label>
          </div>

          {topLevelError ? (
            <div
              className="bg-destructive/10 text-destructive border-destructive/40 rounded-md border p-3 text-sm"
              role="alert"
            >
              {topLevelError}
            </div>
          ) : null}

          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              {t("common:actions.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting
                ? t("users.dialog.submit_busy")
                : isCreate
                  ? t("users.dialog.submit_create")
                  : t("users.dialog.submit_edit")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
