import { useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/lib/query/keys";
import { ErrorState } from "@/components/feedback/ErrorState";

// Shown by the route guards when the boot-time /owner/me probe failed on a
// 5xx/network error (an indeterminate verdict). Retry refetches the probe — the
// observer lives in boot.tsx, so invalidating its key drives the refetch.
export function OwnerProbeError() {
  const queryClient = useQueryClient();
  return (
    <div className="flex min-h-screen items-center justify-center p-8">
      <ErrorState
        className="w-full max-w-md"
        onRetry={() => queryClient.invalidateQueries({ queryKey: queryKeys.owner.me() })}
      />
    </div>
  );
}
