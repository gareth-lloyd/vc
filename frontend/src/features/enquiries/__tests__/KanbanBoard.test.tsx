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
    total: 236,
    items: [
      { id: 1, label: "Alpha" },
      { id: 2, label: "Beta" },
    ],
    footer: <span>Showing 2 of 236</span>,
  },
  { id: "contacted", title: "Contacted", total: 1, items: [{ id: 3, label: "Gamma" }] },
  { id: "quoted", title: "Quoted", total: 0, items: [] },
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
    expect(within(quoted).getByText(/no enquiries/i)).toBeInTheDocument();
  });

  it("badges the column total, not the number of cards it holds", () => {
    // GAP-118: the board is windowed — `items` is one page of the column, so
    // `items.length` under-reports the badge by orders of magnitude.
    renderWithProviders(
      <KanbanBoard<Card>
        columns={columns}
        getItemId={(c) => String(c.id)}
        renderCard={(c) => <div>{c.label}</div>}
      />,
    );
    const newCol = screen.getByTestId("kanban-column-new");
    expect(within(newCol).getByText("236")).toBeInTheDocument();
    expect(within(newCol).queryByText("2")).not.toBeInTheDocument();
    const contacted = screen.getByTestId("kanban-column-contacted");
    expect(within(contacted).getByText("1")).toBeInTheDocument();
  });

  it("renders a column's footer under its cards", () => {
    renderWithProviders(
      <KanbanBoard<Card>
        columns={columns}
        getItemId={(c) => String(c.id)}
        renderCard={(c) => <div>{c.label}</div>}
      />,
    );
    const newCol = screen.getByTestId("kanban-column-new");
    expect(within(newCol).getByText("Showing 2 of 236")).toBeInTheDocument();
    // A column without one renders nothing extra.
    const contacted = screen.getByTestId("kanban-column-contacted");
    expect(within(contacted).queryByText(/showing/i)).not.toBeInTheDocument();
  });
});
