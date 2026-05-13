import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api/errors";
import { useVerifyTfa } from "./hooks";
import { useAuthStore } from "./store";
import { useNextPath } from "./useNextPath";

export function TfaChallengePage() {
  const navigate = useNavigate();
  const nextPath = useNextPath();
  const pending = useAuthStore((s) => s.pendingTfa);
  const verify = useVerifyTfa();
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    document.title = "Two-factor · Villa Collective";
  }, []);

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
      setError(err instanceof ApiError ? err.detail : "Verification failed");
    }
  };

  return (
    <div className="bg-muted/30 flex min-h-screen items-center justify-center px-4">
      <form
        onSubmit={onSubmit}
        className="bg-card w-full max-w-sm space-y-6 rounded-lg border p-8 shadow-sm"
        noValidate
      >
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Two-factor code</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Enter the 6-digit code from your authenticator app.
          </p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="code">Code</Label>
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

        {error ? (
          <div
            className="bg-destructive/10 text-destructive border-destructive/40 rounded-md border p-3 text-sm"
            role="alert"
          >
            {error}
          </div>
        ) : null}

        <Button type="submit" className="w-full" disabled={verify.isPending || code.length < 4}>
          {verify.isPending ? "Verifying…" : "Verify"}
        </Button>
      </form>
    </div>
  );
}
