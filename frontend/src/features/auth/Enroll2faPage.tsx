import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { QRCodeSVG } from "qrcode.react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api/errors";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { useConfirmTfaEnrollment, useStartTfaEnrollment } from "./hooks";
import { useNextPath } from "./useNextPath";
import { enrollConfirmInputSchema, type EnrollStartResponse } from "./schemas";

type Phase = "confirm" | "recovery";

export function Enroll2faPage() {
  const { t } = useTranslation("auth");
  const navigate = useNavigate();
  const nextPath = useNextPath();
  const start = useStartTfaEnrollment();
  const confirm = useConfirmTfaEnrollment();
  const [enrollment, setEnrollment] = useState<EnrollStartResponse | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("confirm");
  const [copied, setCopied] = useState(false);
  const startedRef = useRef(false);

  useEffect(() => {
    document.title = t("enroll.page_title");
  }, [t]);

  // Start enrolment exactly once on mount (the ref guards a re-fire that would
  // mint a second secret and invalidate the QR the user is already scanning).
  const beginEnrollment = () => {
    setError(null);
    start
      .mutateAsync()
      .then(setEnrollment)
      .catch(() => setError(t("enroll.start_failed")));
  };
  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    beginEnrollment();
    // beginEnrollment is stable enough for a once-on-mount start (ref-guarded).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onConfirm = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await confirm.mutateAsync(code.trim());
      setPhase("recovery");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t("enroll.confirm_failed"));
    }
  };

  const onCopySecret = async () => {
    if (!enrollment) return;
    try {
      await navigator.clipboard.writeText(enrollment.secret);
      setCopied(true);
    } catch {
      // Clipboard unavailable (insecure context / denied) — the key is shown
      // for manual entry regardless, so swallow.
    }
  };

  const shell = (children: React.ReactNode) => (
    <div className="bg-muted/30 flex min-h-screen items-center justify-center px-4 py-8">
      <div className="bg-card shadow-card w-full max-w-md space-y-6 rounded-lg border p-8">
        {children}
      </div>
    </div>
  );

  if (phase === "recovery" && enrollment) {
    return shell(
      <>
        <div>
          <h1 className="font-serif text-2xl font-semibold tracking-tight">
            {t("enroll.recovery_title")}
          </h1>
          <p className="text-muted-foreground mt-1 text-sm">{t("enroll.recovery_intro")}</p>
        </div>
        <ul className="bg-muted grid grid-cols-2 gap-2 rounded-md p-4 font-mono text-sm">
          {enrollment.recovery_codes.map((rc) => (
            <li key={rc}>{rc}</li>
          ))}
        </ul>
        <Button className="w-full" onClick={() => navigate(nextPath, { replace: true })}>
          {t("enroll.recovery_ack")}
        </Button>
      </>,
    );
  }

  return shell(
    <>
      <div>
        <h1 className="font-serif text-2xl font-semibold tracking-tight">{t("enroll.title")}</h1>
        <p className="text-muted-foreground mt-1 text-sm">{t("enroll.intro")}</p>
      </div>

      {enrollment ? (
        <>
          <div className="flex justify-center rounded-md bg-white p-4">
            <QRCodeSVG value={enrollment.provisioning_uri} size={176} />
          </div>
          <div className="space-y-2">
            <Label>{t("enroll.secret_label")}</Label>
            <div className="flex items-center gap-2">
              <code className="bg-muted flex-1 overflow-x-auto rounded px-2 py-1 font-mono text-sm">
                {enrollment.secret}
              </code>
              <Button type="button" variant="outline" size="sm" onClick={onCopySecret}>
                {copied ? t("enroll.copied") : t("enroll.copy")}
              </Button>
            </div>
          </div>

          <form onSubmit={onConfirm} className="space-y-4" noValidate>
            <div className="space-y-2">
              <Label htmlFor="tfa-enroll-code">{t("enroll.code_label")}</Label>
              <Input
                id="tfa-enroll-code"
                inputMode="numeric"
                autoComplete="one-time-code"
                autoFocus
                maxLength={6}
                value={code}
                // Keep the field to digits so a paste can't post a non-numeric
                // code the schema gate below would only silently disable.
                onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                aria-invalid={!!error}
              />
            </div>
            <FormErrorAlert message={error} />
            <Button
              type="submit"
              className="w-full"
              disabled={confirm.isPending || !enrollConfirmInputSchema.safeParse({ code }).success}
            >
              {confirm.isPending ? t("enroll.confirming") : t("enroll.confirm")}
            </Button>
          </form>
        </>
      ) : (
        <div className="space-y-3">
          <p className="text-muted-foreground text-sm">{t("enroll.starting")}</p>
          <FormErrorAlert message={error} />
          {error && (
            <Button
              type="button"
              variant="outline"
              className="w-full"
              disabled={start.isPending}
              onClick={beginEnrollment}
            >
              {t("enroll.retry")}
            </Button>
          )}
        </div>
      )}
    </>,
  );
}
