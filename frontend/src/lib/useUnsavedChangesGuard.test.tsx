import { useState } from "react";
import { Link } from "react-router-dom";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderWithDataRouter } from "@/test/render";
import { useUnsavedChangesGuard } from "./useUnsavedChangesGuard";

function Probe({ initialDirty }: { initialDirty: boolean }) {
  const [dirty, setDirty] = useState(initialDirty);
  const guard = useUnsavedChangesGuard(dirty);
  return (
    <div>
      <span data-testid="blocked">{guard.blocked ? "blocked" : "free"}</span>
      <span data-testid="dirty">{dirty ? "dirty" : "clean"}</span>
      <Link to="/other">go</Link>
      <button type="button" onClick={guard.proceed}>
        proceed
      </button>
      <button type="button" onClick={guard.reset}>
        reset
      </button>
      <button type="button" onClick={() => setDirty(false)}>
        make clean
      </button>
    </div>
  );
}

function setup(initialDirty: boolean) {
  const user = userEvent.setup();
  const rendered = renderWithDataRouter(
    [
      { path: "/edit", element: <Probe initialDirty={initialDirty} /> },
      { path: "/other", element: <div>other-page</div> },
    ],
    { route: "/edit" },
  );
  return { user, ...rendered };
}

function dispatchBeforeUnload(): boolean {
  const event = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(event);
  return event.defaultPrevented;
}

describe("useUnsavedChangesGuard", () => {
  it("lets navigation through when clean", async () => {
    const { user, router } = setup(false);
    expect(screen.getByTestId("blocked")).toHaveTextContent("free");

    await user.click(screen.getByRole("link", { name: "go" }));

    expect(await screen.findByText("other-page")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/other");
  });

  it("blocks navigation when dirty", async () => {
    const { user, router } = setup(true);

    await user.click(screen.getByRole("link", { name: "go" }));

    await waitFor(() => expect(screen.getByTestId("blocked")).toHaveTextContent("blocked"));
    expect(router.state.location.pathname).toBe("/edit");
    expect(screen.queryByText("other-page")).not.toBeInTheDocument();
  });

  it("reset() cancels the pending navigation and stays put", async () => {
    const { user, router } = setup(true);
    await user.click(screen.getByRole("link", { name: "go" }));
    await waitFor(() => expect(screen.getByTestId("blocked")).toHaveTextContent("blocked"));

    await user.click(screen.getByRole("button", { name: "reset" }));

    await waitFor(() => expect(screen.getByTestId("blocked")).toHaveTextContent("free"));
    expect(router.state.location.pathname).toBe("/edit");
    expect(screen.getByTestId("dirty")).toHaveTextContent("dirty");
  });

  it("proceed() completes the pending navigation", async () => {
    const { user, router } = setup(true);
    await user.click(screen.getByRole("link", { name: "go" }));
    await waitFor(() => expect(screen.getByTestId("blocked")).toHaveTextContent("blocked"));

    await user.click(screen.getByRole("button", { name: "proceed" }));

    expect(await screen.findByText("other-page")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/other");
  });

  it("tolerates settling the same block twice (double-click on Discard)", async () => {
    const { user, router } = setup(true);
    await user.click(screen.getByRole("link", { name: "go" }));
    await waitFor(() => expect(screen.getByTestId("blocked")).toHaveTextContent("blocked"));

    // Two synchronous clicks before the router's transition re-renders: the
    // second must be a no-op, not an "Invalid blocker state transition" throw.
    const proceed = screen.getByRole("button", { name: "proceed" });
    expect(() => {
      fireEvent.click(proceed);
      fireEvent.click(proceed);
    }).not.toThrow();

    expect(await screen.findByText("other-page")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/other");
  });

  it("auto-resets a pending block when the caller becomes clean", async () => {
    const { user, router } = setup(true);
    await user.click(screen.getByRole("link", { name: "go" }));
    await waitFor(() => expect(screen.getByTestId("blocked")).toHaveTextContent("blocked"));

    await user.click(screen.getByRole("button", { name: "make clean" }));

    await waitFor(() => expect(screen.getByTestId("blocked")).toHaveTextContent("free"));
    expect(router.state.location.pathname).toBe("/edit");
    // Once clean, a fresh navigation goes straight through.
    await user.click(screen.getByRole("link", { name: "go" }));
    expect(await screen.findByText("other-page")).toBeInTheDocument();
  });

  it("prevents beforeunload while dirty, not when clean", async () => {
    const { user } = setup(true);
    expect(dispatchBeforeUnload()).toBe(true);

    await user.click(screen.getByRole("button", { name: "make clean" }));

    await waitFor(() => expect(dispatchBeforeUnload()).toBe(false));
  });

  it("removes the beforeunload listener on unmount while still dirty", () => {
    const { unmount } = setup(true);
    expect(dispatchBeforeUnload()).toBe(true);
    unmount();
    expect(dispatchBeforeUnload()).toBe(false);
  });
});
