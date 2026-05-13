import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ColumnDef, SortingState } from "@tanstack/react-table";
import { renderWithProviders } from "@/test/render";
import { DataTable } from "../DataTable";

interface Row {
  id: number;
  name: string;
}

const columns: ColumnDef<Row>[] = [
  { accessorKey: "id", header: "ID", enableSorting: true },
  { accessorKey: "name", header: "Name", enableSorting: true },
];

const noopSort: (s: SortingState) => void = () => {};

describe("DataTable", () => {
  it("renders rows from data", () => {
    renderWithProviders(
      <DataTable
        columns={columns}
        data={[
          { id: 1, name: "Casa Norte" },
          { id: 2, name: "Villa Azul" },
        ]}
        pageIndex={0}
        pageCount={1}
        sorting={[]}
        onSortingChange={noopSort}
        onPageChange={() => {}}
      />,
    );
    expect(screen.getByText("Casa Norte")).toBeInTheDocument();
    expect(screen.getByText("Villa Azul")).toBeInTheDocument();
  });

  it("renders skeleton rows when loading", () => {
    renderWithProviders(
      <DataTable
        columns={columns}
        data={undefined}
        isLoading
        pageIndex={0}
        pageCount={1}
        sorting={[]}
        onSortingChange={noopSort}
        onPageChange={() => {}}
      />,
    );
    expect(screen.getAllByTestId("data-table-skeleton-row")).toHaveLength(5);
  });

  it("renders emptyContent when not loading and no data", () => {
    renderWithProviders(
      <DataTable
        columns={columns}
        data={[]}
        pageIndex={0}
        pageCount={1}
        sorting={[]}
        onSortingChange={noopSort}
        onPageChange={() => {}}
        emptyContent={<div>No matches</div>}
      />,
    );
    expect(screen.getByText("No matches")).toBeInTheDocument();
  });

  it("calls onPageChange with next index when Next clicked", async () => {
    const onPageChange = vi.fn();
    renderWithProviders(
      <DataTable
        columns={columns}
        data={[{ id: 1, name: "A" }]}
        pageIndex={0}
        pageCount={3}
        sorting={[]}
        onSortingChange={noopSort}
        onPageChange={onPageChange}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /next page/i }));
    expect(onPageChange).toHaveBeenCalledWith(1);
  });

  it("calls onSortingChange when a sortable header is clicked", async () => {
    const onSortingChange = vi.fn();
    renderWithProviders(
      <DataTable
        columns={columns}
        data={[{ id: 1, name: "A" }]}
        pageIndex={0}
        pageCount={1}
        sorting={[]}
        onSortingChange={onSortingChange}
        onPageChange={() => {}}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Name" }));
    expect(onSortingChange).toHaveBeenCalled();
    const next = onSortingChange.mock.calls[0][0] as SortingState;
    expect(next[0]).toMatchObject({ id: "name", desc: false });
  });

  it("invokes onRowClick when a row is clicked", async () => {
    const onRowClick = vi.fn();
    renderWithProviders(
      <DataTable
        columns={columns}
        data={[{ id: 1, name: "A" }]}
        pageIndex={0}
        pageCount={1}
        sorting={[]}
        onSortingChange={noopSort}
        onPageChange={() => {}}
        onRowClick={onRowClick}
      />,
    );
    await userEvent.click(screen.getByText("A"));
    expect(onRowClick).toHaveBeenCalledWith({ id: 1, name: "A" });
  });
});
