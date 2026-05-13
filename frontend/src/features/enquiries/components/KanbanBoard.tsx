import { useMemo, useState, type ReactNode } from "react";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { cn } from "@/lib/cn";

export interface KanbanColumn<T> {
  id: string;
  title: string;
  items: T[];
}

interface KanbanBoardProps<T> {
  columns: KanbanColumn<T>[];
  renderCard: (item: T) => ReactNode;
  // Board doesn't mutate state — parent owns the data and the optimistic update/rollback.
  onMoveItem?: (itemId: string, fromColId: string, toColId: string) => void;
  getItemId: (item: T) => string;
}

interface DraggableCardProps {
  id: string;
  children: ReactNode;
}

function DraggableCard({ id, children }: DraggableCardProps) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id });
  return (
    <div
      ref={setNodeRef}
      {...attributes}
      {...listeners}
      className={cn("touch-none", isDragging && "opacity-50")}
      data-kanban-card-id={id}
    >
      {children}
    </div>
  );
}

interface DroppableColumnProps {
  id: string;
  title: string;
  count: number;
  children: ReactNode;
}

function DroppableColumn({ id, title, count, children }: DroppableColumnProps) {
  const { setNodeRef, isOver } = useDroppable({ id });
  return (
    <div
      ref={setNodeRef}
      className={cn(
        "bg-muted/40 flex w-72 flex-shrink-0 flex-col rounded-lg border p-2",
        isOver ? "border-foreground" : "border-border",
      )}
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

export function KanbanBoard<T>({
  columns,
  renderCard,
  onMoveItem,
  getItemId,
}: KanbanBoardProps<T>) {
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));
  const [activeId, setActiveId] = useState<string | null>(null);

  const itemIndex = useMemo(() => {
    const out = new Map<string, { item: T; columnId: string }>();
    for (const col of columns) {
      for (const item of col.items) {
        out.set(getItemId(item), { item, columnId: col.id });
      }
    }
    return out;
  }, [columns, getItemId]);

  const activeItem = activeId ? itemIndex.get(activeId)?.item : undefined;

  function handleDragStart(event: DragStartEvent) {
    setActiveId(String(event.active.id));
  }

  function handleDragEnd(event: DragEndEvent) {
    setActiveId(null);
    const overId = event.over?.id;
    const itemId = String(event.active.id);
    if (overId == null) return;
    const targetCol = String(overId);
    const entry = itemIndex.get(itemId);
    if (!entry) return;
    if (entry.columnId === targetCol) return;
    onMoveItem?.(itemId, entry.columnId, targetCol);
  }

  return (
    <DndContext sensors={sensors} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
      <div className="flex gap-3 overflow-x-auto pb-4">
        {columns.map((col) => (
          <DroppableColumn key={col.id} id={col.id} title={col.title} count={col.items.length}>
            {col.items.map((item) => {
              const id = getItemId(item);
              return (
                <DraggableCard key={id} id={id}>
                  {renderCard(item)}
                </DraggableCard>
              );
            })}
            {col.items.length === 0 ? (
              <div className="text-muted-foreground rounded border border-dashed px-2 py-6 text-center text-xs">
                Drop here
              </div>
            ) : null}
          </DroppableColumn>
        ))}
      </div>
      <DragOverlay>
        {activeItem ? <div className="opacity-80">{renderCard(activeItem)}</div> : null}
      </DragOverlay>
    </DndContext>
  );
}
