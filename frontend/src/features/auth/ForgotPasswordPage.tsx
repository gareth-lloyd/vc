import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { forgotPasswordInputSchema, type ForgotPasswordInput } from "./schemas";
import { useRequestPasswordReset } from "./hooks";

export function ForgotPasswordPage() {
  const { t } = useTranslation("auth");

  const form = useForm<ForgotPasswordInput>({
    resolver: zodResolver(forgotPasswordInputSchema),
    defaultValues: { email: "" },
  });

  const requestReset = useRequestPasswordReset();
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  const onSubmit = form.handleSubmit(async (values) => {
    setTopLevelError(null);
    try {
      await requestReset.mutateAsync(values.email);
      // The endpoint is silent on whether the email is registered, so the
      // confirmation is deliberately neutral — no account-enumeration signal.
      setSent(true);
    } catch (error) {
      const { detail } = applyApiErrorToForm(form, error);
      setTopLevelError(detail);
    }
  });

  useEffect(() => {
    document.title = t("forgot_password.page_title");
  }, [t]);

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
        {sent ? (
          <div className="bg-card shadow-card w-full max-w-sm space-y-4 rounded-lg border p-8">
            <h2 className="text-foreground font-serif text-2xl font-semibold tracking-tight">
              {t("forgot_password.sent_title")}
            </h2>
            <p className="text-muted-foreground text-sm">{t("forgot_password.sent_body")}</p>
            <Link to="/login" className="text-primary text-sm hover:underline">
              {t("forgot_password.back_to_login")}
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
                {t("forgot_password.title")}
              </h2>
              <p className="text-muted-foreground mt-1 text-sm">{t("forgot_password.subtitle")}</p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="email">{t("forgot_password.email_label")}</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                autoFocus
                {...form.register("email")}
                aria-invalid={!!form.formState.errors.email}
              />
              {form.formState.errors.email ? (
                <p className="text-destructive text-sm" role="alert">
                  {form.formState.errors.email.message}
                </p>
              ) : null}
            </div>

            <FormErrorAlert message={topLevelError} />

            <Button type="submit" className="w-full" disabled={requestReset.isPending}>
              {requestReset.isPending
                ? t("forgot_password.submitting")
                : t("forgot_password.submit")}
            </Button>

            <div className="text-center">
              <Link to="/login" className="text-muted-foreground text-sm hover:underline">
                {t("forgot_password.back_to_login")}
              </Link>
            </div>
          </form>
        )}
      </section>
    </div>
  );
}
