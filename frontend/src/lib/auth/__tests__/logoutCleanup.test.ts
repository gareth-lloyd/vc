import { registerLogoutCleanup, runLogoutCleanups } from "../logoutCleanup";

describe("logoutCleanup registry", () => {
  it("runs every registered cleanup on runLogoutCleanups", () => {
    const first = vi.fn();
    const second = vi.fn();
    const unregisterFirst = registerLogoutCleanup(first);
    const unregisterSecond = registerLogoutCleanup(second);

    runLogoutCleanups();

    expect(first).toHaveBeenCalledTimes(1);
    expect(second).toHaveBeenCalledTimes(1);
    unregisterFirst();
    unregisterSecond();
  });

  it("re-registering the same function does not run it twice", () => {
    const fn = vi.fn();
    const unregister = registerLogoutCleanup(fn);
    registerLogoutCleanup(fn);

    runLogoutCleanups();

    expect(fn).toHaveBeenCalledTimes(1);
    unregister();
  });

  it("unregister removes the cleanup", () => {
    const fn = vi.fn();
    const unregister = registerLogoutCleanup(fn);
    unregister();

    runLogoutCleanups();

    expect(fn).not.toHaveBeenCalled();
  });
});
