import { type ReactNode } from "react";
import { useTranslation } from "react-i18next";

export interface KanbanColumn<T> {
  id: string;
  title: string;
  items: T[];
}

interface KanbanBoardProps<T> {
  columns: KanbanColumn<T>[];
  renderCard: (item: T) => ReactNode;
  getItemId: (item: T) => string;
}

interface ColumnProps {
  id: string;
  title: string;
  count: number;
  children: ReactNode;
}

function Column({ id, title, count, children }: ColumnProps) {
  return (
    <div
      className="bg-muted/40 border-border flex w-72 flex-shrink-0 flex-col rounded-lg border p-2"
      data-kanban-column-id={id}
      data-testid={`kanban-column-${id}`}
    >
      <div className="mb-2 flex items-center justify-between px-1">
        <h3 className="text-foreground text-sm font-semibold">{title}</h3>
        <span className="text-muted-foreground text-xs">{count}</span>
      </div>
      <div className="flex flex-1 flex-col gap-2 overflow-y-auto">{children}</div>
    </div>
  );
}

// Read-only lane board: cards group by status and click through to the detail
// page, where transitions are performed with their required context. There is no
// drag-and-drop — the forward transitions (quoted, converted) are records of work
// done elsewhere and each needs captured metadata, so a generic "move the card"
// gesture is the wrong affordance for them.
export function KanbanBoard<T>({ columns, renderCard, getItemId }: KanbanBoardProps<T>) {
  const { t } = useTranslation("enquiries");

  return (
    <div className="flex gap-3 overflow-x-auto pb-4">
      {columns.map((col) => (
        <Column key={col.id} id={col.id} title={col.title} count={col.items.length}>
          {col.items.map((item) => (
            <div key={getItemId(item)}>{renderCard(item)}</div>
          ))}
          {col.items.length === 0 ? (
            <div className="text-muted-foreground rounded border border-dashed px-2 py-6 text-center text-xs">
              {t("kanban.empty_column")}
            </div>
          ) : null}
        </Column>
      ))}
    </div>
  );
}
