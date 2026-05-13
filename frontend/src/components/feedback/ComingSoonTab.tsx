import { EmptyState } from "./EmptyState";

export function ComingSoonTab({ tabName }: { tabName: string }) {
  return (
    <div className="p-6">
      <EmptyState
        title={`${tabName} — coming in next phase`}
        description={`This tab will be wired up in a future phase.`}
      />
    </div>
  );
}
