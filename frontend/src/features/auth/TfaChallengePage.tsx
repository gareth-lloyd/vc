import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api/errors";
import { useVerifyTfa } from "./hooks";
import { useAuthStore } from "./store";
import { useNextPath } from "./useNextPath";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";

export function TfaChallengePage() {
  const { t } = useTranslation("auth");
  const navigate = useNavigate();
  const nextPath = useNextPath();
  const pending = useAuthStore((s) => s.pendingTfa);
  const verify = useVerifyTfa();
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    document.title = t("tfa.page_title");
  }, [t]);

  if (!pending) {
    return <Navigate to="/login" replace />;
  }

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await verify.mutateAsync({ challenge_token: pending.challengeToken, code });
      navigate(nextPath, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t("tfa.verification_failed"));
    }
  };

  return (
    <div className="bg-muted/30 flex min-h-screen items-center justify-center px-4">
      <form
        onSubmit={onSubmit}
        className="bg-card shadow-card w-full max-w-sm space-y-6 rounded-lg border p-8"
        noValidate
      >
        <div>
          <h1 className="font-serif text-2xl font-semibold tracking-tight">{t("tfa.title")}</h1>
          <p className="text-muted-foreground mt-1 text-sm">{t("tfa.prompt")}</p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="code">{t("tfa.code_label")}</Label>
          <Input
            id="code"
            inputMode="numeric"
            autoComplete="one-time-code"
            autoFocus
            value={code}
            onChange={(e) => setCode(e.target.value)}
            aria-invalid={!!error}
          />
        </div>

        <FormErrorAlert message={error} />

        <Button type="submit" className="w-full" disabled={verify.isPending || code.length < 4}>
          {verify.isPending ? t("tfa.submitting") : t("tfa.submit")}
        </Button>
      </form>
    </div>
  );
}
