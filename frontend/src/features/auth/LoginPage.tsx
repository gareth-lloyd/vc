import { useEffect, useState } from "react";
import { useController, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { loginInputSchema, type LoginInput } from "./schemas";
import { useLogin } from "./hooks";
import { useNextPath } from "./useNextPath";

export function LoginPage() {
  const { t } = useTranslation("auth");
  const navigate = useNavigate();
  const nextPath = useNextPath();

  const form = useForm<LoginInput>({
    resolver: zodResolver(loginInputSchema),
    defaultValues: { email: "", password: "", remember: false },
  });
  const rememberCtrl = useController({ control: form.control, name: "remember" });

  const login = useLogin();
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  const onSubmit = form.handleSubmit(async (values) => {
    setTopLevelError(null);
    try {
      const result = await login.mutateAsync(values);
      if (result.tfa_required) {
        navigate("/login/2fa", { state: { next: nextPath } });
        return;
      }
      navigate(nextPath, { replace: true });
    } catch (error) {
      const { detail } = applyApiErrorToForm(form, error);
      setTopLevelError(detail);
    }
  });

  useEffect(() => {
    document.title = t("login.page_title");
  }, [t]);

  return (
    <div className="bg-background grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      {/* Photography stand-in: sun-washed gradient as a placeholder until
          real villa photography is integrated. The wordmark sits on top
          in cream Fraunces — first impression. */}
      <aside className="bg-sunwash relative hidden overflow-hidden lg:flex lg:flex-col lg:justify-between lg:p-12">
        <div className="relative z-10 text-neutral-50">
          <p className="font-mono text-[10px] tracking-[0.32em] uppercase opacity-80">
            Est. MMXXVI · Mediterranean &amp; Beyond
          </p>
          <h1
            className="mt-3 font-serif text-6xl leading-[0.95] font-semibold"
            style={{ fontVariationSettings: '"opsz" 144' }}
          >
            Villa
            <br />
            <span className="text-accent-200">Collective</span>
          </h1>
        </div>

        {/* Pull-quote at the foot of the hero panel — the villa-rental
            brand needs a voice, not just a logo. */}
        <figure className="relative z-10 max-w-md text-neutral-50">
          <blockquote className="font-serif text-2xl leading-snug italic">
            “The kind of place where the light, the wine, and the people all conspire to slow you
            down.”
          </blockquote>
          <figcaption className="mt-3 text-xs tracking-[0.18em] uppercase opacity-80">
            From the Collective's field notes
          </figcaption>
        </figure>

        {/* Decorative grain overlaid on the gradient. */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-30 mix-blend-overlay"
          style={{
            backgroundImage:
              "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240' viewBox='0 0 240 240'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 0.5 0'/></filter><rect width='100%25' height='100%25' filter='url(%23n)'/></svg>\")",
          }}
        />
      </aside>

      {/* Form panel — linen background, generous breathing room. */}
      <section className="flex items-center justify-center px-6 py-12 sm:px-12">
        <form
          onSubmit={onSubmit}
          className="bg-card shadow-card rounded-asym w-full max-w-sm space-y-6 border p-8"
          noValidate
        >
          <div>
            <p className="text-brand-700 font-script text-2xl leading-none">Bonjour</p>
            <h2
              className="text-foreground mt-1 font-serif text-3xl font-semibold tracking-tight"
              style={{ fontVariationSettings: '"opsz" 144' }}
            >
              {t("login.title")}
            </h2>
            <p className="text-muted-foreground mt-2 text-sm">{t("login.subtitle")}</p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="email">{t("login.fields.email")}</Label>
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

          <div className="space-y-2">
            <Label htmlFor="password">{t("login.fields.password")}</Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              {...form.register("password")}
              aria-invalid={!!form.formState.errors.password}
            />
            {form.formState.errors.password ? (
              <p className="text-destructive text-sm" role="alert">
                {form.formState.errors.password.message}
              </p>
            ) : null}
          </div>

          <div className="flex items-center justify-between">
            <label className="flex cursor-pointer items-center gap-2 text-sm">
              <Checkbox
                checked={!!rememberCtrl.field.value}
                onCheckedChange={(v) => rememberCtrl.field.onChange(v === true)}
              />
              <span>{t("login.remember_device")}</span>
            </label>
            <Link to="/forgot-password" className="text-muted-foreground text-sm hover:underline">
              {t("login.forgot_password")}
            </Link>
          </div>

          {topLevelError ? (
            <div
              className="bg-destructive/10 text-destructive border-destructive/40 rounded-md border p-3 text-sm"
              role="alert"
            >
              {topLevelError}
            </div>
          ) : null}

          <Button type="submit" className="w-full" disabled={login.isPending}>
            {login.isPending ? t("login.submitting") : t("login.submit")}
          </Button>
        </form>
      </section>
    </div>
  );
}
