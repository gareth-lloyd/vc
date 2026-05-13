import { useEffect, useState } from "react";
import { useController, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { loginInputSchema, type LoginInput } from "./schemas";
import { useLogin } from "./hooks";
import { useNextPath } from "./useNextPath";

export function LoginPage() {
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
    document.title = "Sign in · Villa Collective";
  }, []);

  return (
    <div className="bg-muted/30 flex min-h-screen items-center justify-center px-4">
      <form
        onSubmit={onSubmit}
        className="bg-card w-full max-w-sm space-y-6 rounded-lg border p-8 shadow-sm"
        noValidate
      >
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Sign in</h1>
          <p className="text-muted-foreground mt-1 text-sm">Villa Collective management</p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="email">Email</Label>
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
          <Label htmlFor="password">Password</Label>
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
            <span>Remember device</span>
          </label>
          <Link to="/forgot-password" className="text-muted-foreground text-sm hover:underline">
            Forgot password?
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
          {login.isPending ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </div>
  );
}
