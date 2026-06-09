import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { useListParams } from "../useListParams";

function wrapper(initial: string) {
  return ({ children }: { children: ReactNode }) => (
    <MemoryRouter initialEntries={[initial]}>{children}</MemoryRouter>
  );
}

describe("useListParams", () => {
  it("debounces the search box into ?q= and resets pagination", async () => {
    const { result } = renderHook(() => useListParams(), { wrapper: wrapper("/x?page=3") });

    act(() => result.current.setSearch("ada"));
    await waitFor(() => expect(result.current.params.get("q")).toBe("ada"));
    expect(result.current.params.get("page")).toBeNull();
  });

  it("updateParam writes a value (clearing page) and treats __all__ as unset", async () => {
    const { result } = renderHook(() => useListParams(), { wrapper: wrapper("/x?page=2") });

    act(() => result.current.updateParam("status", "sent"));
    await waitFor(() => expect(result.current.params.get("status")).toBe("sent"));
    expect(result.current.params.get("page")).toBeNull();

    act(() => result.current.updateParam("status", "__all__"));
    await waitFor(() => expect(result.current.params.get("status")).toBeNull());
  });

  it("goToPage writes a 1-based page and drops page 0", async () => {
    const { result } = renderHook(() => useListParams(), { wrapper: wrapper("/x") });

    act(() => result.current.goToPage(2));
    await waitFor(() => expect(result.current.params.get("page")).toBe("3"));

    act(() => result.current.goToPage(0));
    await waitFor(() => expect(result.current.params.get("page")).toBeNull());
  });
});
