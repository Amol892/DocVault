import type { ReactNode } from "react";
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClientError } from "@/api/client";
import { ToastContext } from "../useToast";
import { useDebouncedValue } from "../useDebouncedValue";
import { useSafeAction } from "../useSafeAction";

describe("useDebouncedValue", () => {
  afterEach(() => vi.useRealTimers());

  it("only updates after the value has been stable for the delay", () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(({ v }) => useDebouncedValue(v, 300), {
      initialProps: { v: "a" },
    });
    expect(result.current).toBe("a");

    rerender({ v: "ab" });
    act(() => vi.advanceTimersByTime(299));
    expect(result.current).toBe("a");

    rerender({ v: "abc" }); // typing again restarts the wait
    act(() => vi.advanceTimersByTime(299));
    expect(result.current).toBe("a");

    act(() => vi.advanceTimersByTime(1));
    expect(result.current).toBe("abc");
  });
});

describe("useSafeAction", () => {
  const toast = vi.fn();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <ToastContext.Provider value={toast}>{children}</ToastContext.Provider>
  );
  afterEach(() => toast.mockReset());

  it("returns the value and shows no toast on success", async () => {
    const { result } = renderHook(() => useSafeAction(), { wrapper });
    const res = await result.current(async () => 42);
    expect(res).toEqual({ ok: true, value: 42 });
    expect(toast).not.toHaveBeenCalled();
  });

  it("turns a failure into a toast instead of an unhandled rejection", async () => {
    const { result } = renderHook(() => useSafeAction(), { wrapper });
    const res = await result.current(async () => {
      throw new ApiClientError(403, "FORBIDDEN", "Only admins can do that");
    });
    expect(res).toEqual({ ok: false });
    expect(toast).toHaveBeenCalledWith("Only admins can do that");
  });
});
