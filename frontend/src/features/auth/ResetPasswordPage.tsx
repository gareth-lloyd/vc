import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api/errors";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { resetPasswordInputSchema, type ResetPasswordInput } from "./schemas";
import { useConfirmPasswordReset } from "./hooks";

// Both failures come back as 400 with a distinct code (the expired case is
// deliberately NOT a 401 — that would trip the global session-dead redirect).
// Either one means the link can't be used, so route both to the same state.
const TOKEN_ERROR_CODES = new Set(["password_reset_token_expired", "password_reset_token_invalid"]);

export function ResetPasswordPage() {
  const { t } = useTranslation("auth");
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const form = useForm<ResetPasswordInput>({
    resolver: zodResolver(resetPasswordInputSchema),
    defaultValues: { new_password: "", confirm_password: "" },
  });

  const confirmReset = useConfirmPasswordReset();
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  const [linkRejected, setLinkRejected] = useState(false);

  const onSubmit = form.handleSubmit(async (values) => {
    setTopLevelError(null);
    try {
      await confirmReset.mutateAsync({ token, new_password: values.new_password });
      toast.success(t("reset_password.success_toast"));
      navigate("/login", { replace: true });
    } catch (error) {
      if (error instanceof ApiError && TOKEN_ERROR_CODES.has(error.code)) {
        setLinkRejected(true);
        return;
      }
      const { detail } = applyApiErrorToForm(form, error);
      setTopLevelError(detail);
    }
  });

  useEffect(() => {
    document.title = t("reset_password.page_title");
  }, [t]);

  const showInvalidLink = token === "" || linkRejected;

  return (
    <div className="bg-background grid min-h-screen lg:grid-cols-[1fr_1fr]">
      <aside className="bg-sidebar text-sidebar-foreground hidden lg:flex lg:items-end lg:p-12">
        <span
          className="font-serif text-3xl leading-none font-semibold"
          style={{ fontVariationSettings: '"opsz" 144' }}
        >
          Villa Collective
        </span>
      </aside>

      <section className="flex items-center justify-center px-6 py-12 sm:px-12">
        {showInvalidLink ? (
          <div className="bg-card shadow-card w-full max-w-sm space-y-4 rounded-lg border p-8">
            <h2 className="text-foreground font-serif text-2xl font-semibold tracking-tight">
              {t("reset_password.invalid_link_title")}
            </h2>
            <p className="text-muted-foreground text-sm">{t("reset_password.invalid_link_body")}</p>
            <Link to="/forgot-password" className="text-primary text-sm hover:underline">
              {t("reset_password.request_new_link")}
            </Link>
          </div>
        ) : (
          <form
            onSubmit={onSubmit}
            className="bg-card shadow-card w-full max-w-sm space-y-6 rounded-lg border p-8"
            noValidate
          >
            <div>
              <h2 className="text-foreground font-serif text-2xl font-semibold tracking-tight">
                {t("reset_password.title")}
              </h2>
              <p className="text-muted-foreground mt-1 text-sm">{t("reset_password.subtitle")}</p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="new_password">{t("reset_password.new_password_label")}</Label>
              <Input
                id="new_password"
                type="password"
                autoComplete="new-password"
                autoFocus
                {...form.register("new_password")}
                aria-invalid={!!form.formState.errors.new_password}
              />
              {form.formState.errors.new_password ? (
                <p className="text-destructive text-sm" role="alert">
                  {form.formState.errors.new_password.message}
                </p>
              ) : null}
            </div>

            <div className="space-y-2">
              <Label htmlFor="confirm_password">{t("reset_password.confirm_password_label")}</Label>
              <Input
                id="confirm_password"
                type="password"
                autoComplete="new-password"
                {...form.register("confirm_password")}
                aria-invalid={!!form.formState.errors.confirm_password}
              />
              {form.formState.errors.confirm_password ? (
                <p className="text-destructive text-sm" role="alert">
                  {form.formState.errors.confirm_password.message}
                </p>
              ) : null}
            </div>

            <FormErrorAlert message={topLevelError} />

            <Button type="submit" className="w-full" disabled={confirmReset.isPending}>
              {confirmReset.isPending ? t("reset_password.submitting") : t("reset_password.submit")}
            </Button>
          </form>
        )}
      </section>
    </div>
  );
}
