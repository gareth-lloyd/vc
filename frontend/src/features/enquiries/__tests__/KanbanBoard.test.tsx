import { describe, expect, it } from "vitest";
import { screen, within } from "@testing-library/react";
import { renderWithProviders } from "@/test/render";
import { KanbanBoard, type KanbanColumn } from "../components/KanbanBoard";

interface Card {
  id: number;
  label: string;
}

const columns: KanbanColumn<Card>[] = [
  {
    id: "new",
    title: "New",
    items: [
      { id: 1, label: "Alpha" },
      { id: 2, label: "Beta" },
    ],
  },
  { id: "contacted", title: "Contacted", items: [{ id: 3, label: "Gamma" }] },
  { id: "quoted", title: "Quoted", items: [] },
];

describe("KanbanBoard", () => {
  it("renders one column per entry with the right items", () => {
    renderWithProviders(
      <KanbanBoard<Card>
        columns={columns}
        getItemId={(c) => String(c.id)}
        renderCard={(c) => <div data-testid={`card-${c.id}`}>{c.label}</div>}
      />,
    );

    const newCol = screen.getByTestId("kanban-column-new");
    expect(within(newCol).getByText("New")).toBeInTheDocument();
    expect(within(newCol).getByText("Alpha")).toBeInTheDocument();
    expect(within(newCol).getByText("Beta")).toBeInTheDocument();

    const contacted = screen.getByTestId("kanban-column-contacted");
    expect(within(contacted).getByText("Gamma")).toBeInTheDocument();

    const quoted = screen.getByTestId("kanban-column-quoted");
    expect(within(quoted).getByText(/drop here/i)).toBeInTheDocument();
  });

  it("shows column item counts", () => {
    renderWithProviders(
      <KanbanBoard<Card>
        columns={columns}
        getItemId={(c) => String(c.id)}
        renderCard={(c) => <div>{c.label}</div>}
      />,
    );
    const newCol = screen.getByTestId("kanban-column-new");
    expect(within(newCol).getByText("2")).toBeInTheDocument();
    const contacted = screen.getByTestId("kanban-column-contacted");
    expect(within(contacted).getByText("1")).toBeInTheDocument();
  });
});
